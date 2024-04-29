import logging
import datetime
import phonenumbers

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..utils import learner_utils

_logger = logging.getLogger(__name__)


class Dossier(models.Model):
    _inherit = 'gestion.formation.dossier'
    
    @api.model
    def _get_status_list(self):
        return self.STATUS
    
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

    exam_session_id = fields.Many2one('examen.session', store=True, readonly=True)
    gender = fields.Selection(GENDER, string='genre')
    birth_day = fields.Date(string='date de naissance')
    nationality = fields.Many2one('res.country','Pays de nationalité')
    motivation = fields.Selection(learner_utils.MOTIVATIONS_LIST) 
    n_cni_ts = fields.Char('N° de CNI/TS')
    maternal_langage = fields.Char("langue maternelle")
    insciption_file = fields.Binary(
        string='Fichier'
    )
    status_exam = fields.Selection(learner_utils.STATUS_EXAM, default="none")
    status = fields.Selection(selection=_get_status_list, string='Statut',
                              default='ACCEPTED', tracking=True, readonly=False, store=True,
                              compute="_compute_status")
    
    inscriptions = fields.Many2many("examen.inscription", relation='inscription_participant_edof_rel')
    last_annulation_day = fields.Date("Delay d'annulation se l'inscription", store=True, compute="_compute_last_annulation_day")
    nbr_covocation = fields.Integer("Nombres de convocation envoyé", default=0)

    convocation_id = fields.Many2one(
                        'convocation.history',
                        delegate=True,
                        ondelete="cascade",
                        default=lambda self: self.env['convocation.history'].sudo().create({})
                        )
    
    @api.depends("status_exam")
    def _compute_status(self):
        for rec in self:
            if rec.status_exam == "register_paid":
                rec.status = 'exam_to_confirm'
            if rec.status_exam == "exam_sheduled":
                rec.status = 'exam_scheduled'
            if rec.status_exam == "exam_to_reshedule":
                rec.status = 'exam_to_reschedule'


    def send_exam_convocation(self):
        template = self.env.ref('exam_polylangue.email_template_exam_convocation_cpf')
        for rec in self:
            result_mails_su, result_messages = rec.message_post_with_template(template.id )

            if not rec.nbr_covocation :
                rec.nbr_covocation = 0
            rec.nbr_covocation += 1

            if not rec.convocation_id:
                rec.convocation_id = self.env['convocation.history'].create({})
            rec.convocation_id.add_convocation_line({
                'date': datetime.datetime.now(),
                'way': 'email',
                'reason': 'Convocation a un examen',
                'message_id': result_messages.id,
                # 'convocation_id': rec.id
            })

    def action_view_convocation(self):
        self.ensure_one()
        if not self.convocation_id :  
            self.convocation_id = self.env['convocation.history'].create({})
        print(f" ====== {self.convocation_id}")
        return self.convocation_id.action_view_convocation()

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
    
    def validate_exam(self):
        for rec in self:
            if rec.status_exam != 'register_paid':
                raise models.ValidationError("Impossible de valider cette inscription")
            else :
                rec.status_exam = 'exam_sheduled'
                rec.send_exam_convocation()

    def cancel_exam(self):
        for rec in self:
            rec.inscriptions = [(6, 0, [x.id for x in rec.inscriptions if x.session_id !=  rec.exam_session_id])]
            rec.sudo().write({
                'status_exam': 'exam_to_reshedule',
                'exam_date': None,
                'time': None,
                'exam_center_id': None,
            })

    def cancel_ins(self):
        for rec in self:
            if rec.last_annulation_day < datetime.datetime.now().date():
                raise models.ValidationError('"Vous ne pouvez plus annuler cette inscription')
            rec.cancel_exam()
            

    @api.depends('exam_session_id.date')
    def _compute_last_annulation_day(self):
        min_interval = int(self.env['ir.config_parameter'].sudo().get_param("exam_polylangue.minimal_day_before_anunlation"))
        for rec in self:
            if rec.exam_session_id:
                rec.last_annulation_day = rec.exam_session_id.date - datetime.timedelta(days=min_interval)
