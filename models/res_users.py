from odoo import fields, models


class ResUsersInherit(models.Model):
    _inherit = 'res.users'

    is_examiner = fields.Boolean(string="Est Un Examinateur ?", default=False)