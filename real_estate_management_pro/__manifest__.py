# -*- coding: utf-8 -*-
{
    'name': 'Real Estate Management',
    'version': '18.0.1.0.0',
    'category': 'Real Estate/Real Estate',
    'live_test_url': 'https://youtu.be/8Gp2J6WrP1c',
    'images': ['static/description/banner.png'],
    'summary': 'Large-scale real estate suite: properties, contracts, '
               'collections, maintenance, renovations and analytics.',
    'description': """
Real Estate Management
======================
End-to-end management of a real estate portfolio:

* Analytic dashboard (kanban + graph + pivot) of properties, contracts,
  pending collections and rent/sale balances.
* Property records with geolocation (latitude/longitude) ready for Map view.
* Rental and sale contracts with an automatic collection schedule and
  delinquency (overdue) alerts shown in red.
* Directory separating tenants, owners, maintenance providers and own staff.
* Maintenance ticketing for property incidents.
* Renovation projects and tasks (works and furniture) per property.
* QWeb PDF reports for contracts and property financial balances.
""",
    'author': 'Higa Solutions',
    'website': 'https://higa.group',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'calendar',
    ],
    'data': [
        # Security
        'security/real_estate_security.xml',
        'security/ir.model.access.csv',
        # Master data
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        # Views
        'views/real_estate_property_type_views.xml',
        'views/real_estate_property_views.xml',
        'views/real_estate_contract_views.xml',
        'views/real_estate_payment_views.xml',
        'views/real_estate_maintenance_views.xml',
        'views/real_estate_renovation_views.xml',
        'views/res_partner_views.xml',
        'views/real_estate_visit_views.xml',
        'views/real_estate_dashboard_views.xml',
        # 'views/real_estate_property_map_views.xml',  # Requires 'web_map' (Enterprise)
        # Reports
        'report/real_estate_report_templates.xml',
        'report/real_estate_contract_report.xml',
        'report/real_estate_balance_report.xml',
        # Menus (must load last: references actions + reports)
        'views/real_estate_menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}

