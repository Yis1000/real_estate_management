# -*- coding: utf-8 -*-
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestRealEstateCommon(TransactionCase):
    """Shared fixture: one owner, one tenant and one property."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env['res.partner']
        cls.owner = Partner.create({
            'name': 'Owner Test',
            'is_property_owner': True,
        })
        cls.tenant = Partner.create({
            'name': 'Tenant Test',
            'is_property_tenant': True,
        })
        cls.provider = Partner.create({
            'name': 'Provider Test',
            'is_maintenance_provider': True,
        })
        cls.property_type = cls.env['real.estate.property.type'].create({
            'name': 'Flat',
        })
        cls.property = cls.env['real.estate.property'].create({
            'name': 'Gran Via 12',
            'property_type_id': cls.property_type.id,
            'owner_id': cls.owner.id,
            'state': 'available',
            'rent_price': 1000.0,
            'sale_price': 240000.0,
        })

    def _new_contract(self, **overrides):
        """A one-year rental contract, draft, not yet scheduled."""
        vals = {
            'property_id': self.property.id,
            'tenant_id': self.tenant.id,
            'contract_type': 'rent',
            'date_start': date(2026, 1, 1),
            'date_end': date(2026, 12, 31),
            'payment_day': 1,
            'rent_amount': 1000.0,
        }
        vals.update(overrides)
        return self.env['real.estate.contract'].create(vals)


@tagged('post_install', '-at_install')
class TestProperty(TestRealEstateCommon):

    def test_code_sequence_and_display_name(self):
        """A new property takes its reference from the sequence, and the
        display name carries it so pickers stay unambiguous."""
        self.assertTrue(self.property.code.startswith('PROP/'), self.property.code)
        self.assertEqual(
            self.property.display_name,
            '[%s] %s' % (self.property.code, self.property.name))

    def test_gross_yield(self):
        """Annual rent over sale price, and no division by zero when the
        property is not for sale."""
        # 1000 * 12 / 240000 * 100 = 5%
        self.assertAlmostEqual(self.property.gross_yield, 5.0, places=4)
        self.property.sale_price = 0.0
        self.assertEqual(self.property.gross_yield, 0.0)

    def test_is_new_flag(self):
        """Freshly created properties are flagged as new; old ones are not."""
        self.assertTrue(self.property.is_new)
        self.env.cr.execute(
            'UPDATE real_estate_property SET create_date = %s WHERE id = %s',
            (fields.Datetime.now() - relativedelta(days=30), self.property.id))
        # Invalidate the whole record: is_new is not stored, so dropping only
        # create_date from the cache would leave the stale computed value.
        self.property.invalidate_recordset()
        self.assertFalse(self.property.is_new)

    def test_related_counts(self):
        """The smart-button counters follow the related records."""
        self.assertEqual(self.property.contract_count, 0)
        contract = self._new_contract()
        self.env['real.estate.maintenance'].create({
            'property_id': self.property.id, 'title': 'Leak'})
        self.env['real.estate.renovation'].create({
            'property_id': self.property.id, 'name': 'Kitchen'})
        self.env['real.estate.visit'].create({
            'property_id': self.property.id, 'contact_id': self.tenant.id})
        self.assertEqual(self.property.contract_count, 1)
        self.assertEqual(self.property.maintenance_count, 1)
        self.assertEqual(self.property.renovation_count, 1)
        self.assertEqual(self.property.visit_count, 1)
        self.assertEqual(self.property.contract_ids, contract)

    def test_active_contract_and_tenant(self):
        """Only a running contract makes the property occupied."""
        contract = self._new_contract()
        self.assertFalse(self.property.active_contract_id)
        self.assertFalse(self.property.current_tenant_id)
        contract.action_confirm()
        self.assertEqual(self.property.active_contract_id, contract)
        self.assertEqual(self.property.current_tenant_id, self.tenant)

    def test_financial_summary(self):
        """Net balance is collected income minus maintenance and renovation."""
        contract = self._new_contract()
        contract.action_confirm()
        payments = contract.payment_ids
        payments[0].action_register_payment()
        payments[1].action_register_payment()
        self.env['real.estate.maintenance'].create({
            'property_id': self.property.id, 'title': 'Boiler', 'cost': 300.0})
        renovation = self.env['real.estate.renovation'].create({
            'property_id': self.property.id, 'name': 'Bathroom'})
        self.env['real.estate.renovation.task'].create({
            'renovation_id': renovation.id, 'name': 'Tiles', 'actual_cost': 200.0})

        self.assertEqual(self.property.total_collected, 2000.0)
        self.assertEqual(self.property.total_pending, 10000.0)
        self.assertEqual(self.property.maintenance_cost, 300.0)
        self.assertEqual(self.property.renovation_cost, 200.0)
        self.assertEqual(self.property.net_balance, 1500.0)

    def test_state_actions(self):
        self.property.action_set_unavailable()
        self.assertEqual(self.property.state, 'unavailable')
        self.property.action_set_available()
        self.assertEqual(self.property.state, 'available')


@tagged('post_install', '-at_install')
class TestContractSchedule(TestRealEstateCommon):

    def test_name_sequence(self):
        contract = self._new_contract()
        self.assertTrue(contract.name.startswith('CON/'), contract.name)

    def test_payment_day_constraint(self):
        """Days 29-31 do not exist in every month, so they are rejected."""
        contract = self._new_contract()
        for bad_day in (0, 29, 31):
            with self.assertRaises(UserError), self.env.cr.savepoint():
                contract.write({'payment_day': bad_day})
                contract.flush_recordset()

    def test_rent_schedule_is_monthly(self):
        """A twelve-month contract yields twelve collections, one per month,
        on the requested day, each for the monthly rent.

        This also covers the translation crash: _generate_payment_schedule
        calls _() while holding a date, which used to raise outside an HTTP
        request. Running it from a test is exactly that situation."""
        contract = self._new_contract(payment_day=5)
        contract._generate_payment_schedule()
        payments = contract.payment_ids.sorted('due_date')

        self.assertEqual(len(payments), 12)
        self.assertEqual(set(payments.mapped('amount')), {1000.0})
        self.assertEqual(payments[0].due_date, date(2026, 1, 5))
        self.assertEqual(payments[-1].due_date, date(2026, 12, 5))
        for payment in payments:
            self.assertEqual(payment.due_date.day, 5)
        # Descriptions are translated strings built in the same method.
        self.assertTrue(all(payments.mapped('description')))

    def test_first_due_date_never_precedes_the_start(self):
        """A contract starting mid-month does not bill for a day already past."""
        contract = self._new_contract(
            date_start=date(2026, 1, 20), date_end=date(2026, 3, 31),
            payment_day=1)
        contract._generate_payment_schedule()
        payments = contract.payment_ids.sorted('due_date')
        self.assertEqual(payments[0].due_date, date(2026, 1, 20))
        self.assertEqual(payments[1].due_date, date(2026, 2, 1))

    def test_payment_day_is_capped_at_28(self):
        contract = self._new_contract(payment_day=28)
        contract._generate_payment_schedule()
        self.assertEqual(
            contract.payment_ids.sorted('due_date')[1].due_date, date(2026, 2, 28))

    def test_sale_schedule_is_a_single_payment(self):
        contract = self._new_contract(
            contract_type='sale', sale_amount=240000.0, rent_amount=0.0,
            date_end=False)
        contract._generate_payment_schedule()
        self.assertEqual(len(contract.payment_ids), 1)
        self.assertEqual(contract.payment_ids.amount, 240000.0)
        self.assertEqual(contract.payment_ids.due_date, contract.date_start)

    def test_rent_schedule_needs_its_inputs(self):
        """Without an end date or a rent there is nothing to schedule, and the
        user is told so instead of silently getting an empty plan."""
        contract = self._new_contract(date_end=False)
        with self.assertRaises(UserError):
            contract._generate_payment_schedule()

    def test_regenerating_keeps_what_was_already_paid(self):
        """Re-running the schedule must not wipe collected money."""
        contract = self._new_contract()
        contract._generate_payment_schedule()
        paid = contract.payment_ids.sorted('due_date')[0]
        paid.action_register_payment()

        contract.rent_amount = 1200.0
        contract._generate_payment_schedule()

        self.assertIn(paid, contract.payment_ids)
        self.assertEqual(paid.amount, 1000.0)
        self.assertEqual(len(contract.payment_ids), 13)
        pending = contract.payment_ids - paid
        self.assertEqual(set(pending.mapped('amount')), {1200.0})


@tagged('post_install', '-at_install')
class TestContractWorkflow(TestRealEstateCommon):

    def test_confirm_rental_occupies_the_property(self):
        contract = self._new_contract()
        contract.action_confirm()
        self.assertEqual(contract.state, 'running')
        self.assertEqual(self.property.state, 'rented')
        self.assertEqual(len(contract.payment_ids), 12)

    def test_confirm_sale_marks_the_property_sold(self):
        contract = self._new_contract(
            contract_type='sale', sale_amount=240000.0, date_end=False)
        contract.action_confirm()
        self.assertEqual(self.property.state, 'sold')

    def test_close_frees_the_property(self):
        contract = self._new_contract()
        contract.action_confirm()
        contract.action_close()
        self.assertEqual(contract.state, 'done')
        self.assertEqual(self.property.state, 'available')

    def test_cancel_drops_the_uncollected_lines(self):
        """Cancelling voids what is still owed but leaves history alone."""
        contract = self._new_contract()
        contract.action_confirm()
        paid = contract.payment_ids.sorted('due_date')[0]
        paid.action_register_payment()

        contract.action_cancel()

        self.assertEqual(contract.state, 'cancelled')
        self.assertEqual(paid.state, 'paid')
        self.assertEqual(
            set((contract.payment_ids - paid).mapped('state')), {'cancelled'})

    def test_set_to_draft(self):
        contract = self._new_contract()
        contract.action_confirm()
        contract.action_set_to_draft()
        self.assertEqual(contract.state, 'draft')


@tagged('post_install', '-at_install')
class TestContractPaymentState(TestRealEstateCommon):

    def test_payment_state_follows_the_collections(self):
        """no_payment -> on_track -> overdue -> paid, with the matching totals."""
        contract = self._new_contract()
        self.assertEqual(contract.payment_state, 'no_payment')

        contract.action_confirm()
        self.assertEqual(contract.payment_state, 'on_track')
        self.assertEqual(contract.payment_count, 12)
        self.assertEqual(contract.amount_pending, 12000.0)
        self.assertFalse(contract.is_overdue)
        self.assertEqual(contract.next_payment_date, date(2026, 1, 1))

        payments = contract.payment_ids.sorted('due_date')
        payments[0].state = 'overdue'
        self.assertEqual(contract.payment_state, 'overdue')
        self.assertTrue(contract.is_overdue)
        self.assertEqual(contract.overdue_count, 1)
        self.assertEqual(contract.amount_overdue, 1000.0)

        payments.action_register_payment()
        self.assertEqual(contract.payment_state, 'paid')
        self.assertEqual(contract.amount_collected, 12000.0)
        self.assertEqual(contract.amount_pending, 0.0)
        self.assertFalse(contract.next_payment_date)


@tagged('post_install', '-at_install')
class TestPayment(TestRealEstateCommon):

    def test_register_and_reset(self):
        contract = self._new_contract()
        contract.action_confirm()
        payment = contract.payment_ids.sorted('due_date')[0]

        payment.action_register_payment()
        self.assertEqual(payment.state, 'paid')
        self.assertEqual(payment.payment_date, fields.Date.context_today(payment))

        payment.action_reset_pending()
        self.assertEqual(payment.state, 'pending')
        self.assertFalse(payment.payment_date)

    def test_days_overdue(self):
        """Counted only while the money is still owed."""
        contract = self._new_contract()
        contract.action_confirm()
        payment = contract.payment_ids.sorted('due_date')[0]
        payment.due_date = fields.Date.context_today(payment) - timedelta(days=10)

        self.assertEqual(payment.days_overdue, 10)
        payment.action_register_payment()
        self.assertEqual(payment.days_overdue, 0)

    def test_cron_flags_overdue_and_warns_the_agent(self):
        """The daily job moves due lines to overdue, posts on the contract and
        leaves the agent an activity."""
        contract = self._new_contract()
        contract.action_confirm()
        payments = contract.payment_ids.sorted('due_date')
        today = fields.Date.context_today(contract)
        payments[0].due_date = today - timedelta(days=5)
        payments[1].due_date = today + timedelta(days=5)
        messages_before = len(contract.message_ids)

        self.env['real.estate.payment']._cron_check_overdue_payments()

        self.assertEqual(payments[0].state, 'overdue')
        self.assertEqual(payments[1].state, 'pending')
        self.assertEqual(contract.payment_state, 'overdue')
        self.assertGreater(len(contract.message_ids), messages_before)
        self.assertTrue(contract.activity_ids)

    def test_cron_leaves_settled_lines_alone(self):
        contract = self._new_contract()
        contract.action_confirm()
        payment = contract.payment_ids.sorted('due_date')[0]
        payment.due_date = fields.Date.context_today(contract) - timedelta(days=5)
        payment.action_register_payment()

        self.env['real.estate.payment']._cron_check_overdue_payments()

        self.assertEqual(payment.state, 'paid')


@tagged('post_install', '-at_install')
class TestPartner(TestRealEstateCommon):

    def test_role_label(self):
        """The directory label lists every hat the contact wears."""
        self.assertEqual(self.owner.real_estate_role, 'Owner')
        self.owner.is_maintenance_provider = True
        self.assertEqual(self.owner.real_estate_role, 'Owner, Provider')
        plain = self.env['res.partner'].create({'name': 'Nobody'})
        self.assertFalse(plain.real_estate_role)

    def test_counts(self):
        self.assertEqual(self.owner.owned_property_count, 1)
        self.assertEqual(self.tenant.tenant_contract_count, 0)
        self._new_contract()
        self.assertEqual(self.tenant.tenant_contract_count, 1)


@tagged('post_install', '-at_install')
class TestMaintenance(TestRealEstateCommon):

    def test_sequence_and_resolution(self):
        ticket = self.env['real.estate.maintenance'].create({
            'property_id': self.property.id,
            'title': 'Broken tap',
            'maintenance_type': 'plumbing',
            'provider_id': self.provider.id,
        })
        self.assertTrue(ticket.name.startswith('TICK/'), ticket.name)
        self.assertEqual(ticket.state, 'new')

        ticket.action_start()
        self.assertEqual(ticket.state, 'in_progress')

        ticket.action_done()
        self.assertEqual(ticket.state, 'done')
        self.assertEqual(ticket.date_resolved, fields.Date.context_today(ticket))

        ticket.action_reset()
        self.assertEqual(ticket.state, 'new')
        self.assertFalse(ticket.date_resolved)

    def test_group_expand_lists_every_column(self):
        """The kanban keeps empty columns visible."""
        states = self.env['real.estate.maintenance']._group_expand_states()
        self.assertEqual(states, ['new', 'in_progress', 'done', 'cancelled'])


@tagged('post_install', '-at_install')
class TestRenovation(TestRealEstateCommon):

    def test_cost_rollup_and_progress(self):
        project = self.env['real.estate.renovation'].create({
            'property_id': self.property.id,
            'name': 'Full refurbishment',
            'budget': 10000.0,
        })
        Task = self.env['real.estate.renovation.task']
        done = Task.create({
            'renovation_id': project.id, 'name': 'Demolition',
            'actual_cost': 3000.0, 'state': 'done'})
        Task.create({
            'renovation_id': project.id, 'name': 'Painting',
            'actual_cost': 1500.0})

        self.assertEqual(project.task_count, 2)
        self.assertEqual(project.task_done_count, 1)
        self.assertEqual(project.progress, 50.0)
        self.assertEqual(project.actual_cost, 4500.0)
        self.assertEqual(project.budget_variance, 5500.0)
        self.assertEqual(done.property_id, self.property)

    def test_progress_without_tasks(self):
        project = self.env['real.estate.renovation'].create({
            'property_id': self.property.id, 'name': 'Empty'})
        self.assertEqual(project.progress, 0.0)

    def test_workflow(self):
        project = self.env['real.estate.renovation'].create({
            'property_id': self.property.id, 'name': 'Roof'})
        project.action_start()
        self.assertEqual(project.state, 'in_progress')
        project.action_done()
        self.assertEqual(project.state, 'done')
        project.action_cancel()
        self.assertEqual(project.state, 'cancelled')


@tagged('post_install', '-at_install')
class TestVisit(TestRealEstateCommon):

    def test_end_date_follows_the_duration(self):
        visit = self.env['real.estate.visit'].create({
            'property_id': self.property.id,
            'contact_id': self.tenant.id,
            'date_start': fields.Datetime.to_datetime('2026-03-01 10:00:00'),
            'duration': 1.5,
        })
        self.assertTrue(visit.name.startswith('VIS/'), visit.name)
        self.assertEqual(
            visit.date_end, fields.Datetime.to_datetime('2026-03-01 11:30:00'))

    def test_colour_tracks_the_status(self):
        """The calendar colour has to change with the workflow."""
        visit = self.env['real.estate.visit'].create({
            'property_id': self.property.id, 'contact_id': self.tenant.id})
        self.assertEqual(visit.color, 4)
        visit.action_confirm()
        self.assertEqual(visit.color, 10)
        visit.action_done()
        self.assertEqual(visit.color, 7)
        visit.action_no_show()
        self.assertEqual(visit.color, 2)
        visit.action_cancel()
        self.assertEqual(visit.color, 1)
        visit.action_reset()
        self.assertEqual(visit.state, 'scheduled')


@tagged('post_install', '-at_install')
class TestDashboard(TestRealEstateCommon):

    def test_kpis_move_with_the_data(self):
        """Counters are read as deltas: the database may already hold records."""
        dashboard = self.env['real.estate.dashboard'].create({})
        before = {
            'properties': dashboard.property_count,
            'contracts': dashboard.contract_count,
            'active': dashboard.active_contract_count,
            'tickets': dashboard.open_tickets,
        }

        contract = self._new_contract()
        contract.action_confirm()
        self.env['real.estate.maintenance'].create({
            'property_id': self.property.id, 'title': 'Leak'})
        dashboard.invalidate_recordset()

        self.assertEqual(dashboard.contract_count, before['contracts'] + 1)
        self.assertEqual(dashboard.active_contract_count, before['active'] + 1)
        self.assertEqual(dashboard.open_tickets, before['tickets'] + 1)
        self.assertEqual(dashboard.rent_running, dashboard.active_contract_count)
        self.assertGreater(dashboard.active_rate, 0.0)

    def test_open_dashboard_returns_a_singleton_action(self):
        action = self.env['real.estate.dashboard'].action_open_dashboard()
        self.assertEqual(action['res_model'], 'real.estate.dashboard')
        self.assertTrue(action['res_id'])
