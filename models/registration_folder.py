import datetime
import logging
import requests
import random
import phonenumbers


from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.osv import expression


class RegistrationFolder(models.Model):
    _inherit = 'edof.registration.folder'

    STATUS = [
        ("INTRAINING", "En formation"),
        ("FINISHED_TRAINING_OR_TO_BE_BILLED", "Sortie de formation / À facturer"),
        ("BLOCK", "Bloqué"),
        ("ACCEPTED", "Accepté"),
        ("EXAM_SCHEDULED", "Examen programmé"),
        ("EXAM_TO_SCHEDULE", "Examen à programmer"),
        ("EXAM_TO_CONFIRM", "Examen à confirmer"),
        ("INSUFFICIENT_LEVEL", "Niveau insuffisant")
    ]

    GENDER = [
        ('male', "Masculin"),
        ('female', "Feminin"),
    ]

    exam_session_id = fields.Many2one('examen.session_id', required=False , readonly=True)
    gender = fields.Selection(GENDER, string='genre' , required=False)
    birth_day = fields.Date(string='date de naissance' , required=False)
    nationality = fields.Many2one('res.country','Pays de nationalité',required=False )
    motivation = fields.Text(required=False)
    n_cni_ts = fields.Char('N° de CNI/TS',required=False)
    insciption_file = fields.Binary(
        string='Fichier',required=False
    )

    @api.model
    def _get_status_list(self):
        # if self.env.user.has_group('edof_data.edof_group_chef_agence') is True:
        #     return [("INTRAINING", "En formation"), ("FINISHED_TRAINING", "Sortie de formation"), ("ACCEPTED", "Accepté"),]
        # else:
        return self.STATUS
