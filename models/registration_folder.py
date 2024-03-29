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
        ("EXAM_TO_RESCHEDULE", "Examen à reprogrammer"),
        ("EXAM_TO_CONFIRM", "Examen à confirmer"),
        ("INSUFFICIENT_LEVEL", "Niveau insuffisant")
    ]

    GENDER = [
        ('male', "Masculin"),
        ('female', "Feminin"),
    ]

    exam_session_id = fields.Many2one('examen.session', required=False , readonly=True)
    gender = fields.Selection(GENDER, string='genre' , required=False)
    birth_day = fields.Date(string='date de naissance' , required=False)
    nationality = fields.Many2one('res.country','Pays de nationalité',required=False )
    motivation = fields.Text(required=False)
    n_cni_ts = fields.Char('N° de CNI/TS',required=False)
    maternal_langage = fields.Char("langue maternelle")
    insciption_file = fields.Binary(
        string='Fichier',required=False
    )

    inscriptions = fields.Many2many("examen.inscription", relation='inscription_participant_hors_cpf_rel')
    last_annulation_day = fields.Date("Delay d'annulation se l'inscription", store=True, compute="_compute_last_annulation_day")
    
    @api.model
    def _get_status_list(self):
        # if self.env.user.has_group('edof_data.edof_group_chef_agence') is True:
        #     return [("INTRAINING", "En formation"), ("FINISHED_TRAINING", "Sortie de formation"), ("ACCEPTED", "Accepté"),]
        # else:
        return self.STATUS
    
    def send_exam_convocation(self):
        template = self.env.ref('exam_polylangue.email_template_exam_convocation_edof')
        for rec in self:
            rec.sudo().message_post_with_template(template.id )

    
    def get_exam_time(self):
        # Convertir le float en secondes
        float_value = self.time
        total_seconds = int(float_value * 3600)

        # Calculer les heures, minutes et secondes
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60

        # Créer un objet time
        time_object = datetime.time(hours, minutes)

        # Formater la chaîne de caractères au format heure
        time_str = time_object.strftime('%H:%M')

        return time_str

    def cancel_ins(self):
        for rec in self:
            if rec.last_annulation_day < datetime.datetime.now().date():
                raise models.ValidationError('"Vous ne pouvez plus annuler cette inscription')

            rec.sudo().write({
                'status': 'EXAM_TO_RESCHEDULE',
                'exam_date': None,
                'time': None,
                'exam_center_id': None,
                'exam_session_id': None
            })
            rec.inscriptions = [(6, 0, [])]

    @api.depends('exam_session_id.date')
    def _compute_last_annulation_day(self):
        min_interval = int(self.env['ir.config_parameter'].sudo().get_param("exam_polylangue.minimal_day_before_anunlation"))
        for rec in self:
            if rec.exam_session_id:
                rec.last_annulation_day = rec.exam_session_id.date - timedelta(days=min_interval)
