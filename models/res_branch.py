from odoo import models, fields


class ResBranchExtend(models.Model):
    _inherit = "res.branch"

    is_exam_center = fields.Boolean("Est un centre d'examen ?", default=False)