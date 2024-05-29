import datetime
import logging
import requests
import random
import phonenumbers

from datetime import timedelta
from ..utils  import learner_utils

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.osv import expression


class DataArchiveEdof(models.Model):
    _inherit = 'edof.data.archive'

    @api.model
    def _get_status_list(self):
        # if self.env.user.has_group('edof_data.edof_group_chef_agence') is True:
        #     return [("INTRAINING", "En formation"), ("FINISHED_TRAINING", "Sortie de formation"), ("ACCEPTED", "Accepté"),]
        # else:
        return self.STATUS

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

    gender = fields.Selection(GENDER, string='Genre' , )

    comments = fields.Text(
        string="Commentaires", 
        store=True
    )
    fass_pass = fields.Selection(
        selection=lambda self: [(str(p.id), p.name) for p in self.env['product.product'].search([('is_pass', '=', True)])],
        string='FAST PASS',
        store=True,
    )
    exam_date = fields.Date(
        string='Date de l\'examen', 
        tracking=True
    )
    status_exam = fields.Selection(
        learner_utils.STATUS_EXAM, 
        default="none"
    )
    exam_session_id = fields.Many2one(
        comodel_name='examen.session', 
        store=True, 
        readonly=True
    )
    insciption_file = fields.Binary(
        string='Fichier'
    )
    inscriptions = fields.Many2many(
        comodel_name="examen.inscription", 
        relation='inscription_participant_archive_edof_rel'
    )
    last_annulation_day = fields.Date(
        "Delay d'annulation se l'inscription", 
        store=True, 
        compute="_compute_last_annulation_day"
    )
    nbr_covocation = fields.Integer(
        string="Nombres de convocations envoyés", 
        default=0
    )
    status = fields.Selection(
        selection=_get_status_list, 
        string='Statut',
        default='ACCEPTED', 
        tracking=True, 
        readonly=False, 
        store=True, 
        compute="_compute_status"
    )
    exam_center_id = fields.Many2one(
        comodel_name="res.branch", 
        string="Lieu d'examen", 
        tracking=True
    )
    time = fields.Float(
        string='Heure Examen', 
        default="10.0"
    )
    convocation_id = fields.Many2one(
        comodel_name='convocation.history',
        delegate=True,
        ondelete="cascade",
        default=lambda self: self.env['convocation.history'].sudo().create({}),
        compute="_compute_convocation",
        store=True
    )
    birth_day = fields.Date(string='Date de naissance')
    nationality = fields.Many2one('res.country','Pays de nationalité')
    motivation = fields.Selection(learner_utils.MOTIVATIONS_LIST) 
    n_cni_ts = fields.Char('N° de CNI/TS')
    insciption_file = fields.Binary(string='Fichier')
    maternal_langage = fields.Char("Langue maternelle")

    @api.model
    def _get_last_selected_fass_pass(self):
        last_record = self.search([], limit=1, order='id desc')
        return last_record.fass_pass if last_record else False

    @api.depends("status_exam")
    def _compute_status(self):
        for rec in self:
            if rec.status_exam == "register_paid":
                rec.status = 'EXAM_TO_CONFIRM'
            if rec.status_exam == "exam_sheduled":
                rec.status = 'EXAM_SCHEDULED'
            if rec.status_exam == "exam_to_reshedule":
                rec.status = 'EXAM_TO_RESCHEDULE'

    def send_exam_convocation(self):
        template = self.env.ref('exam_polylangue.email_template_exam_convocation_archive_edof')
        for rec in self:
            rec.message_post_with_template(template.id )

            if not rec.nbr_covocation :
                rec.nbr_covocation = 0
            rec.nbr_covocation += 1

            subject = "Convocation a un examen"
            address = "{} {} {}".format(rec.exam_center_id.street,rec.exam_center_id.zip , rec.exam_center_id.city)
                
            phone = phonenumbers.format_number(phonenumbers.parse(rec.attendee_phone_number, 'IT'), phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            
            time_string = f"{int(rec.time)}:{int((rec.time - int(rec.time)) * 60):02d}:00"
            message = f""" Bonjour {rec.attendee_first_name} {rec.attendee_last_name},
            Nous sommes heureux de vous confirmer votre inscription à la session d'Examen: de {rec.exam_session_id.examen_id.name} qui se tiiendra le {rec.exam_date} {time_string} a {address}.

            En cas d'indisponibilité ou de renoncement, veuillez nous prévenir le plus rapidement possible (48h avant) à l'adresse suivante: {rec.training_center_id.email} ou au {rec.exam_center_id.phone}
            Pour une annulation dans un délai inférieur, le cours sera considéré comme pris et nous vous demanderons de signer la feuille d'émargement correspondante.
               
            Vous devez impérativement nous fournir par mail avant le test :<br/>
            La copie recto-verso de votre pièce d’identité en cours de validité avec photo et signature. (Carte d’identité, passeport, permis de conduire ou carte de militaire). (L’avoir avec vous également le jour du test)
            Attention ! A défaut de présentation de pièce d’identité ou de retard, nous serons obligés de vous refuser l’accès au test.
            
            Vos résultats seront envoyés par courrier / email, à l’adresse indiquée lors de votre inscription.
               
            Aucun résultat ne sera transmis par téléphone.
                
            Nous restons à votre disposition pour toute information complémentaire.

            
            Bien cordialement, {rec.company_id.partner_id.name}
            
            """
            rec.convocation_id.send_sms_convocation(phone, subject,message  )

    @api.depends("message_ids")
    def _compute_convocation(self):
        for rec in self:
            if not rec.convocation_id:
                rec.convocation_id = self.env['convocation.history'].create({})
            
            for message in rec.message_ids:
                if isinstance(message.subject, str) and "convocation" in message.subject.lower() and \
                    message.id not in rec.convocation_id.convocation_lines.message_id:

                        rec.convocation_id.add_convocation_line({
                            'date': message.date,
                            'way': 'email',
                            'reason': message.subject,
                            'message_id': message.id,
                            # 'convocation_id': rec.id
                        })

    def action_view_convocation(self):
        self.ensure_one()
        if not self.convocation_id :  
            self.convocation_id = self.env['convocation.history'].create({})
        return self.convocation_id.action_view_convocation()

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
                rec.last_annulation_day = rec.exam_session_id.date - timedelta(days=min_interval)