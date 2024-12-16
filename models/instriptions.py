from odoo import fields, models, api, _
from datetime import datetime, timedelta, date
import logging

class inscription(models.Model):
    _name = 'examen.inscription'
    _description = "Inscriptions aux examens"
    _inherit = ['mail.thread', 'mail.activity.mixin']


    STATUS = [
        ('draft', 'Brouillon'),
        ('in_progress', 'En attente'),
        ('confirm', 'Confirmé'),
        ('validate', 'Validé'),
        ('cancel', 'Annulé')
    ]

    PAYMENT_STATE_SELECTION = [
        ('not_paid', 'Non payé'),
        ('in_payment', 'En cour de  Paiement'),
        ('paid', 'Payé'),
        ('partial', 'Partielement payé'),
        ('reversed', 'Reversé'),
        ('invoicing_legacy', "Héritage de l'application de facturation"),
    ]

    session_id = fields.Many2one(comodel_name="examen.session", required=True, tracking=True)

    participant_edof = fields.Many2many("edof.registration.folder", relation='inscription_participant_hors_cpf_rel', tracking=True)
    participant_hors_cpf = fields.Many2many("gestion.formation.dossier", relation='inscription_participant_edof_rel', tracking=True)
    participant_archive_edof = fields.Many2many(comodel_name='edof.data.archive',relation='inscription_edof_data_archive_rel', tracking=True)

    responsable_id = fields.Many2one("res.users", string="Responsable", related='session_id.responsable_id', store=True, tracking=True)
    branch_ids = fields.Many2many("res.branch", string="Branches", related='responsable_id.branch_ids',
                                relation="inscription_branch_rel", column1="inscriptions", column2="branchs", tracking=True)
    
    status = fields.Selection(selection=STATUS, compute="_compute_status", string='Etat', default='draft', store=True, tracking=True)
    # status_payment = fields.Selection(selection=STATUS, compute="_compute_status", string='Etat', default='draft', store=True)
    invoice_id = fields.Many2one('account.move', required=False, default=None, tracking=True)
    status_paiment = fields.Selection(PAYMENT_STATE_SELECTION,readonly=True, compute="_compute_payment_state", store=True, default="not_paid", tracking=True)
    comments = fields.Text(
        string="Commentaires", 
        store=True, tracking=True
    )

    
    def _compute_nbr_insciption(self):
        self.ensure_one()
        return len(self.participant_edof) + len(self.participant_hors_cpf) + len(self.participant_archive_edof)

    def _compute_nbr_edof_and_archive_edof_insciption(self, participant_edof, participant_archive_edof):
        self.ensure_one()
        return len(participant_edof) + len(participant_archive_edof)
    
    def _compute_nbr_hors_cpf_insciption(self):
        self.ensure_one()
        return len(self.participant_hors_cpf)
    
    def get_nbr_inscription_to_session(self):
        self.ensure_one()
        return self.session_id.get_nbr_inscription()
    
    @api.constrains('participant_edof', 'participant_hors_cpf')
    def _check_participant_limits(self):
        for record in self:
            min = record.session_id.min_cand
            max = record.session_id.max_cand
            nbr_cand = record.get_nbr_inscription_to_session()
            if record._compute_nbr_insciption() <= 0:
                raise models.ValidationError(f"Une inscription doit contenir au moins 1 candidat(e)")
            if nbr_cand > max:
                raise models.ValidationError(f"Vous devez inscrire au maximun {max} candidat(s) a cette session. \n Il reste {max - (nbr_cand - record._compute_nbr_insciption()) } place(s) ")
            if nbr_cand < min:
                raise models.ValidationError(f"Vous devez inscrire au minimum {min} candidat(s) a cette session")
            
        return True
    
    @api.onchange('session_id')
    def _check_session_delay(self):
        if isinstance(self.session_id.last_inscription_day, date) and self.session_id.last_inscription_day  < date.today()  and not self.env.user.has_group('base.group_erp_manager'):
            raise models.ValidationError("""Vous êtes hors délais pour inscrire ou confirmer l'inscription des candidats a cette session. Veuillez contacter un admnistrateur pour cela""")

    def _check_required_info_for_inscription(self):
        self.ensure_one()
        for p in self.participant_edof:
            if not p.gender or not p.birth_day or not p.nationality or not p.maternal_langage \
                or not p.motivation or not p.n_cni_ts or not p.insciption_file :
                raise models.ValidationError(f"Les champs 'genre', 'data de naissance', 'pays de nationalité', 'motivation','N° de CNI/TS', 'langue maternelle' et 'fichier' sont requis pour inscrire un candidat.\
                                 \n Veuillez tous les renseigner chez {p.attendee_last_name} {p.attendee_first_name} et autres")
        
        for p in self.participant_hors_cpf:
            if not p.gender or not p.birth_day or not p.nationality or not p.maternal_langage \
                or not p.motivation or not p.n_cni_ts or not p.insciption_file :
                raise models.ValidationError(f"Les champs 'genre', 'data de naissance', 'pays de nationalité', 'motivation','N° de CNI/TS', 'langue maternelle' et 'fichier' sont requis pour inscrire un candidat.\
                                 \n Veuillez tous les renseigner chez {p.first_name} {p.last_name} et autres")
        return True
    
    def _get_invoiced_company(self):
        if self.env['ir.config_parameter'].sudo().get_param("exam_polylangue.choose_session_accounting_comopany") == 'other':
            cmp_id = int(self.env['ir.config_parameter'].sudo().get_param("exam_polylangue.session_accounting_comopany"))
            return self.env['res.company'].sudo().search([('id','=',cmp_id)])
        else :
            return self.env.company

    def _should_be_invoiced(self):
        self.ensure_one()
        not_invoiced_company_id = self._get_invoiced_company().id
        if not_invoiced_company_id and not_invoiced_company_id == self.responsable_id.branch_id.company_id.id:
            return False

        return True
    
    def action_reverse_inscripiton(self):
        self.ensure_one()
        if self.status == 'in_progress':
            self.status = 'draft'

    def send_inscription_details_to_admin(self):
        self.ensure_one()
        if self.status == 'draft':
            self.status = 'in_progress'

    def _validate_inscription(self):
        self.ensure_one()
        
        if not self._should_be_invoiced():
            if self.status != 'confirm' : return    
            self.status = 'validate'

        elif self.invoice_id and self.invoice_id.payment_state == 'paid':
            self.status = 'validate'
        else: 
            return

        for person in self.participant_edof:
            person.sudo().write({
                'status_exam': 'register_paid',
            })

        for person in self.participant_hors_cpf:
            person.sudo().write({
                'status_exam': 'register_paid',
            })

    @api.depends('invoice_id.payment_state')
    def _compute_status(self):
        for record in self:
           record._validate_inscription()
               
    def _get_default_journal(self):
        self.ensure_one()
        journal = self.env['account.journal'].sudo().search([('type','=','sale'), ('company_id','=',self._get_invoiced_company().id)], limit=1)
        if not journal:
            journal = self.env['account.journal'].sudo().create({
                'name': "Inscription examen",
                'code': "INS_E",
                'type': "sale",
                'company_id': self._get_invoiced_company().id
            })

        return journal
    
    def _get_penality_product(self):
        self.ensure_one()
        date_difference = self.session_id.date - datetime.today().date()
        days_difference = date_difference.days
        penality_product = self.env['product.product'].sudo().search([
            ('is_pass','=',True),
             ('penality_limit','>=',days_difference) ], order="penality_limit asc", limit=1)
        return penality_product

    def _search_penality_product(self, product):
        self.ensure_one()
        penality_product = self.env['product.product'].sudo().search(['|', ('name','ilike', product), ('id','ilike', product)], order="penality_limit asc", limit=1)
        return penality_product

    def _get_nbr_already_paid(self):
        """Return the nomber of inscription already paid"""
        self.ensure_one()
        nbr= len( [x for x in self.participant_edof if x.status_exam == "exam_to_reshedule"] ) \
            + len( [x for x in self.participant_hors_cpf if x.status_exam == "exam_to_reshedule"] )
        return nbr
    
    def _get_nbr_already_hors_cpf_paid(self):
        """Return the nomber of inscription already paid"""
        self.ensure_one()
        return len( [x for x in self.participant_hors_cpf if x.status_exam == "exam_to_reshedule"] )

    def _get_nbr_edof_and_rchive_edof_already_paid(self, participant_edof):
        """Return the nomber of inscription already paid"""
        self.ensure_one()
        return len( [x for x in participant_edof if x.status_exam == "exam_to_reshedule"] ) 
        # \
        #         + len(self.participant_archive_edof)
    def write_edof_penality(self):
        penality_count = {}
        if (len(self.participant_edof) > 0):
            for participant in self.participant_edof:
                if participant.fass_pass:
                    if participant.fass_pass not in penality_count:
                        penality_count[participant.fass_pass] = 1
                    else:
                        penality_count[participant.fass_pass] += 1
        for fass_pass, count in penality_count.items():
            participant_penality = self._search_penality_product(fass_pass)
            if participant_penality:
                self.env['account.move.line'].sudo().create({
                    'move_id': self.invoice_id.id,
                    'product_id': participant_penality.id,
                    'name': self._compute_invoice_edof_fas_pass_description(participant_penality),
                    'quantity': count, 
                })

    def write_archive_edof_penality(self):
        penality_count = {}
        if (len(self.participant_archive_edof) > 0):
            for participant in self.participant_archive_edof:
                if participant.fass_pass:
                    if participant.fass_pass not in penality_count:
                        penality_count[participant.fass_pass] = 1
                    else:
                        penality_count[participant.fass_pass] += 1
                        
        for fass_pass, count in penality_count.items():
            participant_penality = self._search_penality_product(fass_pass)
            if participant_penality:
                self.env['account.move.line'].sudo().create({
                    'move_id': self.invoice_id.id,
                    'product_id': participant_penality.id,
                    'name': self._compute_invoice_archive_edof_fas_pass_description(participant_penality),
                    'quantity': count, 
                })

    def write_archive_hors_cpf_penality(self):
        penality_count = {}
        if (len(self.participant_hors_cpf) > 0):
            for participant in self.participant_hors_cpf:
                if participant.fass_pass:
                    if participant.fass_pass not in penality_count:
                        penality_count[participant.fass_pass] = 1
                    else:
                        penality_count[participant.fass_pass] += 1
        for fass_pass, count in penality_count.items():
            participant_penality = self._search_penality_product(fass_pass)
            if participant_penality:
                self.env['account.move.line'].sudo().create({
                    'move_id': self.invoice_id.id,
                    'product_id': participant_penality.id, 
                    'name': self._compute_invoice_hors_cpf_fas_pass_description(participant_penality),
                    'quantity': count, 
                })
                
    def write_edof_and_archive_edof_lines(self):
        # Produit par défaut pour les participants EDOF et Archive EDOF
        default_product_id = self.session_id.examen_id.id

        # Produit particulier pour les participants dont la branche contient "Francisco"
        special_product = self.env['product.product'].search([('name', '=', 'TEF FO')], limit=1)
        special_product_id = special_product.id if special_product else default_product_id

        # Séparation des participants EDOF selon la condition
        edof_special = [p for p in self.participant_edof if 'FRANSIZCA OGRENIYORUM' in p.branch_id.name]
        edof_default = [p for p in self.participant_edof if 'FRANSIZCA OGRENIYORUM' not in p.branch_id.name]

        # Séparation des participants Archive EDOF selon la condition
        archive_edof_special = [p for p in self.participant_archive_edof if 'FRANSIZCA OGRENIYORUM' in p.branch_id.name]
        archive_edof_default = [p for p in self.participant_archive_edof if 'FRANSIZCA OGRENIYORUM' not in p.branch_id.name]


        # Créer les lignes de facture pour les participants qui remplissent la condition 'FRANSIZCA OGRENIYORUM'
        if len(edof_special) > 0 or len(archive_edof_special) > 0:
            self.env['account.move.line'].sudo().create({
                'move_id': self.invoice_id.id,
                'product_id': special_product_id,
                'name': self._compute_invoice_edof_and_archive_edof_description(edof_special, archive_edof_special, special_product),
                'quantity': self._compute_nbr_edof_and_archive_edof_insciption(edof_special, archive_edof_special) - self._get_nbr_edof_and_rchive_edof_already_paid(edof_special),  # Ajustez la quantité selon vos besoins
            })

        # Créer les lignes de facture pour les participants qui ne remplissent pas la condition 'FRANSIZCA OGRENIYORUM'
        if len(edof_default) > 0 or len(archive_edof_default) > 0:
            self.env['account.move.line'].sudo().create({
                'move_id': self.invoice_id.id,
                'product_id': default_product_id,
                'name': self._compute_invoice_edof_and_archive_edof_description(edof_default, archive_edof_default, self.session_id.examen_id),
                'quantity': self._compute_nbr_edof_and_archive_edof_insciption(edof_default, archive_edof_default) - self._get_nbr_edof_and_rchive_edof_already_paid(edof_default),  # Ajustez la quantité selon vos besoins
            })
        
    def _compute_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            invoice_data = {
                'partner_id': self.sudo().responsable_id.branch_id.company_id.partner_id.id, 
                'branch_id': self.sudo().responsable_id.branch_id.id,
                'move_type': 'out_invoice',
                'invoice_date':fields.Date.today(),
                'session_id': self.session_id.id,
                'journal_id': self._get_default_journal().id,
                'company_id': self._get_invoiced_company().id,
                'currency_id': self._get_invoiced_company().currency_id.id,
            }
            try :
                self.invoice_id = self.env['account.move'].sudo().create(invoice_data)
            except Exception as e:
                simalars_partner = self.env['res.partner'].sudo().search([
                    ('name','=',self.sudo().responsable_id.branch_id.company_id.partner_id.name),
                    ('id','!=',self.sudo().responsable_id.branch_id.company_id.partner_id.id),
                    ('is_company','=',True)])
                for partner in simalars_partner:
                    invoice_data['partner_id'] = partner.id
                    try :
                        self.invoice_id = self.env['account.move'].sudo().create(invoice_data)
                        break
                    except Exception as e:
                        raise  models.ValidationError(e)
                    raise models.ValidationError("Impossible de creer la facture")
        # else :
            # for line in self.invoice_id.line_ids:
            #     line.sudo().unlink()    

        # create new product line for exam price   #################################

        # cas du TEF
        if self.session_id.examen_id.name == 'TEF' or self.session_id.examen_id.name == 'TEF IRN':

            # ========================  ecriture comptable: Examen EDOF & Archive EDOF   ===================================

            self.write_edof_and_archive_edof_lines() # ecriture comptable: Examen EDOF & Archive EDOF 
            self.write_edof_penality()          # ecriture comptable: Penalite EDOF 
            self.write_archive_edof_penality()  # ecriture comptable: Penalite ARCHIVE  EDOF
            
            # ========================  ecriture comptable: EXAMEN TEF HORS CPF  ===================================
            
            tef_hcpf_product = self.env['product.product'].search([('name', '=', 'TEF HCPF')], limit=1)
            self.env['account.move.line'].sudo().create({
                'move_id': self.invoice_id.id,
                'product_id': tef_hcpf_product.id,
                'name': self._compute_invoice_hors_cpf_description(),
                'quantity': self._compute_nbr_hors_cpf_insciption() - self._get_nbr_already_hors_cpf_paid(), 
                }
            )
            self.write_archive_hors_cpf_penality() # ecriture comptable: Penalite EXAMEN TEF HORS CPF
       
        # cas d'un autre examen
        else:
            # ========================  ecriture comptable:  EXAMEN EDOF, ARCHIVE EDOF & HORS CPF  ===================================
            self.env['account.move.line'].sudo().create({
                    'move_id': self.invoice_id.id,
                    'product_id': self.session_id.examen_id.id,
                    'name': self._compute_invoice_description(),
                    'quantity': self._compute_nbr_insciption() - self._get_nbr_already_paid(), 
                }
            )
            self.write_edof_penality()             # ecriture comptable: Penalite EDOF 
            self.write_archive_edof_penality()     # ecriture comptable: Penalite ARCHIVE  EDOF
            self.write_archive_hors_cpf_penality() # ecriture comptable: Penalite EXAMEN TEF HORS CPF

                
    def _post_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise models.UserError(_('Aucune facture sur cet inscription'))
        self.invoice_id.sudo().action_post()
        action = self.invoice_id.with_context(discard_logo_check=True).sudo().action_invoice_sent()
        action_context = action['context']

        self.invoice_id.with_context(**action_context).sudo().message_post_with_template(action_context.get('default_template_id'))

    def button_confirm(self, confirm=False):
        self.ensure_one()
        self._check_session_delay()
        if self._check_participant_limits() and  self._check_required_info_for_inscription() and self.responsable_id.branch_id and self.responsable_id.branch_id.company_id:
            if self._should_be_invoiced():
                self._compute_invoice()
                message = ""
                for line in self.invoice_id.line_ids:
                    if line.product_id.is_pass:
                        message = f"""En raison d'une inscription tardive a cette session d'examen, une pénalité de {line.product_id.list_price} {self.invoice_id.currency_id.name} par candidats sera facturé
                        Voulez-vous vraiment continuer ?"""
                # if confirm:
                        
            return self.action_confirm() 
            # return {
            #     'type': 'ir.actions.act_window',
            #     'res_model': 'ir.actions.act_window',
            #     'name': _('Confirmation'),
            #     'view_mode': 'form',
            #     'target': 'new',
            #     'context': {
            #         'default_name': _(message),
            #         'default_type': 'ir.actions.act_window',
            #         'default_res_model': 'votre.model',
            #         'default_res_id': self.id,
            #         'default_method': 'action_confirm',
            #     }
            # }

    def action_confirm(self):
        for insc in self:
            if self._should_be_invoiced():
                if not insc.invoice_id:
                    return False
                insc._post_invoice()
            insc.status='confirm'

            # participant_edof

            for person in self.participant_edof:
                person.sudo().write({
                    'exam_date': self.session_id.date,
                    'time': self.session_id.time,
                    'exam_center_id': self.session_id.exam_center_id.id,
                    'exam_session_id': self.session_id.id
                })

            # participant_archive_edof

            for person in self.participant_archive_edof:
                person.sudo().write({
                    'exam_date': self.session_id.date,
                    'time': self.session_id.time,
                    'exam_center_id': self.session_id.exam_center_id.id,
                    'exam_session_id': self.session_id.id
                })

            # participant_hors_cpf
            old_exam = self.session_id.examen_id
            if self.session_id and self.session_id.examen_id and self.session_id.examen_id.name == 'TEF':
                tef_hcpf_product = self.env['product.product'].search([('name', '=', 'TEF HCPF')], limit=1)
                if tef_hcpf_product:
                    self.session_id.examen_id = tef_hcpf_product
            
            for person in self.participant_hors_cpf:
                person.sudo().write({
                    'exam_date': self.session_id.date,
                    'time': self.session_id.time,
                    'exam_center_id': self.session_id.exam_center_id.id,
                    'exam_session_id': self.session_id.id
                })
            self.session_id.examen_id = old_exam
            self._validate_inscription()
                
    def button_cancel(self):
        for insc in self:
            insc.status='cancel'
            if insc.invoice_id:
                insc.invoice_id.button_cancel()
                insc.invoice_id.unlink()

    def action_view_invoice(self):
        self.ensure_one()
        # action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
        if self.invoice_id:
            action = self.env['ir.actions.actions']._for_xml_id('account.action_move_out_invoice_type')
            form_view = [(self.env.ref('account.view_move_form').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [(state,view) for state,view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = self.invoice_id.id
            return action

    def _compute_invoice_hors_cpf_description(self):
        self.ensure_one()
        title = 'TEF HCPF'
        description = f"Examen: {title if self.session_id.examen_id.name == 'TEF' else self.session_id.examen_id.name}"
        if len(self.participant_hors_cpf) > 0:
            description = f"{description} \n   --- Hors CPF ---"
            for person in self.participant_hors_cpf:
                repro = " (repregrammé) " if person.status_exam == "exam_to_reshedule" else ''
                description = f"""{description}
                {person.last_name} {person.first_name} {person.number} {repro}""" 
        return description

    def _compute_invoice_edof_fas_pass_description(self, product):
        self.ensure_one()
        description = f"{product.name}"
        logging.info(f"prouct : name =  {product.name}, id = {product.id}")
        if len(self.participant_edof) > 0:
            description = f"---- {description} EDOF ----"
            for person in self.participant_edof:
                # logging.info(f"participan edof: name = {person.attendee_last_name} {person.attendee_first_name} fass_pass = {person.fass_pass}")
                if int(person.fass_pass) == int(product.id): 
                    description = f"""{description}
                    {person.attendee_last_name} {person.attendee_first_name}"""   
        return description

    def _compute_invoice_archive_edof_fas_pass_description(self, product):
        self.ensure_one()
        description = f"{product.name}" 
        logging.info(f"prouct : name =  {product.name}, id = {product.id}")
        if len(self.participant_archive_edof) > 0:
            description = f"---- {description} Archive EDOF ----"
            for person in self.participant_archive_edof:
                # logging.info(f"participan edof: name = {person.attendee_last_name} {person.attendee_first_name} fass_pass = {person.fass_pass}")
                if int(person.fass_pass) == int(product.id): 
                    description = f"""{description}
                    {person.attendee_last_name} {person.attendee_first_name}""" 
        return description

    def _compute_invoice_hors_cpf_fas_pass_description(self, product):
        self.ensure_one()
        description = f"{product.name}"
        logging.info(f"prouct : name =  {product.name}, id = {product.id}")
        if len(self.participant_hors_cpf) > 0:
            description = f"---- {description} HORS CPF ----"
            for person in self.participant_hors_cpf:
                if int(person.fass_pass) == int(product.id):
                    # logging.info(f"participan edof: name = {person.last_name} {person.first_name} fass_pass = {person.fass_pass}")
                    description = f"""{description}
                    {person.last_name} {person.first_name}"""   
        return description

    def _compute_invoice_edof_and_archive_edof_description(self, participant_edof, participant_archive_edof, product):
        self.ensure_one()

        description = f"{product.name}"

        if len(participant_edof) > 0:
            description = f"Examen: {description} \n  --- EDOF ---"
            for person in participant_edof:
                repro = " (reprogrammé) " if person.status_exam == "exam_to_reshedule" else ""
                description = f"""{description}
                {person.attendee_last_name} {person.attendee_first_name} {person.folder_number} {repro}"""   

        if len(participant_archive_edof) > 0:
            description = f"{description} \n   --- Archive EDOF ---"
            for person in participant_archive_edof:
                # repro = " (repregrammé) " if person.status_exam == "exam_to_reshedule" else ''
                description = f"""{description}
                {person.attendee_last_name} {person.attendee_first_name} {person.attendee_phone_number}""" 

        return description

    def _compute_invoice_description(self):
        self.ensure_one()
        
        title = 'TEF HCPF'
        description = f"Examen: {title if self.session_id.examen_id.name == 'TEF' else self.session_id.examen_id.name}"
            
        if len(self.participant_edof) > 0:
            description = f"{description} \n  --- EDOF ---"
            for person in self.participant_edof:
                repro = " (reprogrammé) " if person.status_exam == "exam_to_reshedule" else ""
                description = f"""{description}
                {person.attendee_last_name} {person.attendee_first_name} {person.folder_number} {repro}"""   

        if len(self.participant_hors_cpf) > 0:
            description = f"{description} \n   --- Hors CPF ---"
            for person in self.participant_hors_cpf:
                repro = " (repregrammé) " if person.status_exam == "exam_to_reshedule" else ''
                description = f"""{description}
                {person.last_name} {person.first_name} {person.number} {repro}"""   
        
        if len(self.participant_archive_edof) > 0:
            description = f"{description} \n   --- Archive EDOF ---"
            for person in self.participant_archive_edof:
                # repro = " (repregrammé) " if person.status_exam == "exam_to_reshedule" else ''
                description = f"""{description}
                {person.attendee_last_name} {person.attendee_first_name} {person.attendee_phone_number}""" 

        return description
    
    @api.depends('invoice_id.payment_state')
    def _compute_payment_state(self):
        for record in self:
            record.status_paiment = record.invoice_id.payment_state

    