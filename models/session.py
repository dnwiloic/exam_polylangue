from odoo import fields, models, api
from datetime import datetime, timedelta


class Session(models.Model):
    _name = 'examen.session'
    _description = "Session d'examen"

    SESSION_STATES = [
        ('open','Ouvert'),
        ('close','Complet')
    ]

    name = fields.Char("Libelé")
    date = fields.Date("Date de l'examen", required=True)
    time = fields.Float(string='Heure Examen', default="10.0", required=True)
    min_cand = fields.Integer("Nombre minimun de candidat", default=0, required=True)
    max_cand = fields.Integer("Nombre maximun de candidat", default=100, required=True)
    branch_id = fields.Many2one(comodel_name="res.branch",string="Agence", required=True)
    examinateur = fields.Many2one("res.users",required=True)
    examen_id = fields.Many2one("product.product",required=True)
    inscription_ids = fields.One2many(comodel_name='examen.inscription', inverse_name='session_id', default=False)
    have_insc = fields.Boolean(compute="_compute_have_insc", store=True)
    status = fields.Selection(SESSION_STATES, default="open", store=True, compute="_compute_nbr_inscription")
    nbr_cand = fields.Integer("Nombre d'inscriptions", compute="_compute_nbr_inscription", store=True, default=0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            branch_id = self.env['res.branch'].search([('id','=',vals['branch_id'])])
            vals['name'] = f"SESSION - {branch_id.name} - {vals['date']}"
        
        return super(Session, self).create(vals_list)
    # Définir une contrainte
    @api.constrains('date')
    def _check_future_date(self):
        for record in self:
            if record.date:
                # Obtenir la date actuelle
                current_date = datetime.now().date()
                # Ajouter 3 semaines à la date actuelle
                future_date = current_date + timedelta(weeks=3)
                # Vérifier si la date choisie est au moins 3 semaines dans le futur
                if record.date < future_date:
                    raise models.ValidationError("La date doit être au moins 3 semaines dans le futur.")
                
    @api.onchange('date','branch_id','examen_id')
    def _on_session_attr_change(self):
        if self.date and self.branch_id and self.branch_id:
            other_session = self.env['examen.session'].sudo().search([('date','=',self.date),('branch_id','=',self.branch_id.id),('examen_id','=',self.examen_id.id)])
            if other_session:
                raise models.ValidationError(f"Une session d'examen de '{self.examen_id.name}' a déjà été programmé à '{self.branch_id.name}' en date du '{self.date}' ")

    @api.depends('inscription_ids')
    def _compute_status(self):
        for rec in self:
            if rec.get_nbr_inscription() == rec.max_cand:
                rec.status = 'close'

    @api.depends('inscription_ids','inscription_ids.status', 'inscription_ids.participant_edof', 'inscription_ids.participant_hors_cpf')
    def _compute_nbr_inscription(self):
        for rec in self:
            rec.nbr_cand = rec.get_nbr_inscription()
            if rec.nbr_cand >= rec.max_cand:
                rec.status = 'close'
            else:
                rec.status = 'open'


    def get_nbr_inscription(self):
        self.ensure_one()
        nbr_edof = 0
        nbr_cpf = 0
        inscription_ids = self.env['examen.inscription'].sudo().search([('session_id','=',self.id),('status','!=','cancel')])
        for elt in inscription_ids:
            nbr_edof = nbr_edof + len(elt.participant_edof)
            nbr_cpf = nbr_cpf + len(elt.participant_hors_cpf)

        return nbr_edof + nbr_cpf