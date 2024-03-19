from odoo import fields, models, api
from datetime import datetime, timedelta


class Session(models.Model):
    _name = 'examen.session'
    _description = "Session d'examen"

    name = fields.Char("Libelé")
    date = fields.Date("Date de l'examen", required=True)
    time = fields.Float(string='Heure Examen', default="10.0", required=True)
    min_cand = fields.Integer("Nombre minimun de candidat", default=0, required=True)
    max_cand = fields.Integer("Nombre maximun de candidat", default=100, required=True)
    branch_id = fields.Many2one(comodel_name="res.branch",string="Lieu", required=True)
    examinateur = fields.Many2one("res.users",required=True)
    examen_id = fields.Many2one("product.product",required=True)
    inscription_ids = fields.One2many(comodel_name='examen.inscription', inverse_name='session_id', default=False)
    have_insc = fields.Boolean(compute="_compute_have_insc", store=True)

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
                
    @api.depends('inscription_ids.branch_id')
    def _compute_have_insc(self):
        for rec in self:
            if len(rec.inscription_ids) > 0:
                return True
            return False
        

    def get_nbr_inscription(self):
        self.ensure_one()
        return len(self.inscription_ids.participant_edof) + len(self.inscription_ids.participant_hors_cpf)