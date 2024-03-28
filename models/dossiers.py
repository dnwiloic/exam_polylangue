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
        ("exam_to_reschedule", "Examen à reprogrammer"),
        ("exam_to_confirm", "Examen à confirmer"),
        ("insufficient_level", "Niveau insuffisant")
    ]

    GENDER = [
        ('male', "Masculin"),
        ('female', "Feminin"),
    ]
    exam_session_id = fields.Many2one('examen.session', readonly=True)
    gender = fields.Selection(GENDER, string='genre')
    birth_day = fields.Date(string='date de naissance')
    nationality = fields.Many2one('res.country','Pays de nationalité')
    motivation = fields.Text()
    n_cni_ts = fields.Char('N° de CNI/TS')
    maternal_langage = fields.Char("langue maternelle")
    insciption_file = fields.Binary(
        string='Fichier'
    )

    inscriptions = fields.Many2many("examen.inscription", relation='inscription_participant_edof_rel')
    last_annulation_day = fields.Date("Delay d'annulation se l'inscription", store=True, compute="_compute_last_annulation_day")


    @api.model
    def _get_status_list(self):
        return self.STATUS

    def send_exam_convocation(self):
        template = self.env.ref('exam_polylangue.email_template_exam_convocation_cpf')
        for rec in self:
            rec.message_post_with_template(template.id )

    def get_exam_name(self):
        return self.sudo().exam_session_id.examen_id.name
    
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
                'status': 'exam_to_reschedule',
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
                rec.last_annulation_day = rec.exam_session_id.date - datetime.timedelta(days=min_interval)
