from odoo import api, fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    CHOOSE_SESSION_ACCOUNTING_COMPANY = [
        ('current','Société Courrante'),
        ('other', 'Autre société')
    ]
    # limited_day_before_exam_session = fields.Boolean(
    #     string="Empecher la création d'un examen avant un certains nombre de jours ?",
    #     config_parameter='exam_polylangue.enable_day_limit_before_exam')
    nbr_day_before_exam_incription = fields.Integer(
        "Nombre minimum de jour précédant l'inscription à une session d'examen",
        config_parameter='exam_polylangue.minimal_day_before_inscription',
        default="5")
    
    nbr_day_before_exam_annulation = fields.Integer(
        "Nombre minimum de jour précédant l'annulation d'une inscription à un examen",
        config_parameter='exam_polylangue.minimal_day_before_anunlation',
        default="3")
    
    choose_session_accounting_comopany = fields.Selection(
        CHOOSE_SESSION_ACCOUNTING_COMPANY, 
        string="Quelle société facture les inscriptions aux examen?",
        default="current",
        config_parameter='exam_polylangue.choose_session_accounting_comopany',
        required=True,
    )

    session_accounting_comopany = fields.Many2one("res.company",
        string="Société facturant les inscriptions aux examens",
        default=lambda self: self.env['res.company'].sudo().search([],limit=1),
        config_parameter='exam_polylangue.session_accounting_comopany',
    )

    # not_invoiced_branch = fields.Many2many('res.branch',
    #         string="Branches non facturé",
    #         compute="_compute_not_invoiced_branch",
    #         config_parameter='exam_polylangue.exam_not_invoiced_branch',
    #         readonly=False,
    # )

    # @api.depends('choose_session_accounting_comopany','session_accounting_comopany')
    # def _compute_not_invoiced_branch(self):
    #     if self.choose_session_accounting_comopany == 'other' and self.session_accounting_comopany:
    #         branch_ids = self.env['res.branch'].sudo().search([('company_id','=',self.session_accounting_comopany.id)])
    #         self.write({
    #             'champ_many2many': [(6, 0,branch_ids.ids )]
    #         })