import logging
import datetime
import phonenumbers

from odoo import models, fields, api, _
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class Dossier(models.Model):
    _inherit = 'gestion.formation.dossier'
    

    STATUS = [
        ("intraining", "En formation"),
        ("finished_training_or_to_be_billed", "Sortie de formation / À facturer"),
        ("block", "Bloqué"),
        ("accepted", "Accepté"),
        ("exam_scheduled", "Examen programmé"),
        ("exam_to_schedule", "Examen à programmer"),
        ("exam_to_confirm", "Examen à confirmer"),
        ("insufficient_level", "Niveau insuffisant")
    ]

    GENDER = [
        ('male', "Masculin"),
        ('female', "Feminin"),
    ]
    exam_session_id = fields.Many2one('examen.session_id', readonly=True)
    gender = fields.Selection(GENDER, string='genre')
    birth_day = fields.Date(string='date de naissance')
    nationality = fields.Many2one('res.country','Pays de nationalité')
    motivation = fields.Text()
    n_cni_ts = fields.Char('N° de CNI/TS')
    insciption_file = fields.Binary(
        string='Fichier'
    )



    @api.model
    def _get_status_list(self):
        return self.STATUS

