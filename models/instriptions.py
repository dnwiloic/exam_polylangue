from odoo import fields, models, api


class inscription(models.Model):
    _name = 'examen.inscription'
    _description = "Inscriptions aux examens"

    STATE = [
        ('draft', 'Brouillon'),
        ('confirm', 'Confirmé'),
        ('paid', 'Payé'),
        ('cancel', 'Annulé')
    ]

    session_id = fields.Many2one("examen.session", required=True)
    participant_edof = fields.Many2many("edof.registration.folder", relation='inscription_participant_hors_cpf_rel')
    participant_hors_cpf = fields.Many2many("gestion.formation.dossier", relation='inscription_participant_edof_rel')
    branch_id = fields.Many2one("res.branch", string="Agence",required=True, readonly=True, compute="_compute_branch", store=True)
    state = fields.Selection(selection=STATE, compute="_compute_state", string='Etat', default='draft', store=True)
    invoice_id = fields.Many2one('account.move', required=False)

    def _compute_nbr_insciption(self):
        self.ensure_one()
        return len(self.participant_edof) + len(self.participant_hors_cpf)

    @api.depends('session_id')
    def _compute_branch(self):
        for record in self:
            if record.session_id:
                record.branch_id = record.session_id.branch_id
            else :
                record.branch_id = None

    @api.constrains('participant_edof', 'participant_hors_cpf')
    def _check_participant_limits(self):
        for record in self:
            min = record.session_id.min_cand
            max = record.session_id.max_cand
            nbr_cand = record._compute_nbr_insciption()
            if nbr_cand > max:
                raise models.ValidationError(f"Vous devez inscrire au maximun {max} candidat(s) a cette session")
            if nbr_cand < min:
                raise models.ValidationError(f"Vous devez inscrire au minimum {min} candidat(s) a cette session")
        return True
                
    @api.depends('user_id')
    def _compute_user_brach(self):
        for record in self:
            if record.user_id and record.user_id.branch_id:
                record.branch_id = record.user_id.branch_id

    @api.depends('invoice_id.payment_state')
    def _compute_state(self):
        for record in self:
            if record.invoice_id and record.invoice_id.payment_state == 'paid':
                record.state = 'paid'
                for person in record.participant_edof:
                    person.sudo().write({
                        'exam_date': record.session_id.date,
                        'time': record.session_id.time,
                        'exam_center_id': record.session_id.branch_id.id,
                        'status': 'EXAM_SCHEDULED'
                    })
                for person in record.participant_hors_cpf:
                    person.sudo().write({
                        'exam_date': record.session_id.date,
                        'time': record.session_id.time,
                        'exam_center_id': record.session_id.branch_id.id,
                        'status': 'exam_scheduled'
                    })


    def action_confirm(self):
        for insc in self:
            if insc._check_participant_limits() and insc.branch_id and insc.branch_id.company_id:
                
                if not insc.invoice_id:
                    journal = self.env['account.journal'].sudo().search([('name','=',"Achat d'examen"), ('company_id','=',insc.branch_id.company_id.id)])
                    if not journal:
                        journal = self.env['account.journal'].sudo().create({
                            'name': "Achat d'examen",
                            'code': "ACH_EXM",
                            'type': "sale",
                            'company_id': insc.branch_id.company_id.id
                        })
                    
                    invoice_data = {
                        'partner_id': insc.branch_id.company_id.id, 
                        'branch_id': insc.branch_id.id,
                        'move_type': 'out_invoice',
                        'invoice_date':fields.Date.today(),
                        'journal_id': journal.id
                    }
                    insc.invoice_id = self.env['account.move'].sudo().create(invoice_data)

                self.env['account.move.line'].sudo().create({
                        'move_id': insc.invoice_id.id,
                        'product_id': insc.session_id.examen_id.id,
                        'name': insc._compute_invoice_description(),
                        'quantity': insc._compute_nbr_insciption(), 
                        # 'account_id': insc.session_id.examen_id.account_id.id, 
                    }
                )

                # confirm and send email
                insc.invoice_id.sudo().action_post()
                action = insc.invoice_id.with_context(discard_logo_check=True).sudo().action_invoice_sent()
                action_context = action['context']

                insc.invoice_id.with_context(**action_context).message_post_with_template(action_context.get('default_template_id'))
                # template = self.env.ref(insc.invoice_id._get_mail_template())
                # invoice_send_wizard = self.env['account.invoice.send'].with_context(
                #     action_context,
                #     active_ids=[insc.invoice_id.id] 
                # ).sudo().create({'is_print': False, 'template_id': template})
                # print("==================================================================================")
                # print(action_context.get('default_template_id'))
                # print("==================================================================================")
                # # send the invoice
                # invoice_send_wizard.sudo().send_and_print_action()

                if(insc.invoice_id):
                    insc.state='confirm'

    def action_cancel(self):
        for insc in self:
            insc.state='cancel'

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
    

    def _compute_invoice_description(self):
        self.ensure_one()
        description = ""
        if len(self.participant_edof) > 0:
            description = "   --- EDOF ---"
            for person in self.participant_edof:
                description = f"""{description}
                {person.attendee_last_name} {person.attendee_first_name} {person.folder_number}"""   

        if len(self.participant_hors_cpf) > 0:
            description = f"{description} \n   --- Hors CPF ---"
            for person in self.participant_hors_cpf:
                description = f"""{description}
                {person.last_name} {person.first_name} {person.number}"""   

        return description
    
