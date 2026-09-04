# -*- coding: utf-8 -*-
"""Jeu de demonstration pour la verification navigateur de l'Extension 11.

Cree quatre comptes (un par espace du §18) et deroule un parcours complet, plus
quelques dossiers laisses en cours pour que les files du §43 ne soient pas
vides.

Idempotent : relancer ne cree pas de doublon de comptes.
"""
from datetime import timedelta

from odoo import fields

PASSWORD = "demo1234"


def ensure_user(login, name, groups):
    user = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    if not user:
        user = env['res.users'].sudo().create({
            'name': name,
            'login': login,
            'email': '%s@example.org' % login,
            'group_ids': [(6, 0, [env.ref(g).id for g in groups])],
        })
    user.sudo().write({'password': PASSWORD})
    return user


client = ensure_user('demo_client', "Cliente Demo", ['base.group_portal'])
expert = ensure_user('demo_expert', "Expert Demo", ['base.group_portal'])
manager = ensure_user('demo_manager', "Responsable Demo", [
    'base.group_user', 'opex_intervenants.group_mission_manager'])
decideur = ensure_user('demo_comite', "Comite Demo", [
    'base.group_user', 'opex_intervenants.group_mission_committee'])
secretariat = ensure_user('demo_secretariat', "Secretariat Demo", [
    'base.group_user', 'opex_membership.group_secretariat'])

# Un profil expert active : sans le lien sur le partenaire, la reputation
# affichee reste a zero.
Profile = env['opex.innovation.expert.profile'].sudo()
profile = Profile.search([('partner_id', '=', expert.partner_id.id)], limit=1)
if not profile:
    profile = Profile.create({'partner_id': expert.partner_id.id})
expert.partner_id.sudo().expert_profile_id = profile.id

Mission = env['opex.mission.request'].sudo()
Application = env['opex.mission.application'].sudo()
Definition = env['opex.workflow.definition'].sudo()

mission_type = env.ref('opex_intervenants.mission_type_audit')
domaine = env.ref('opex_intervenants.mission_domain_cybersecurite')
today = fields.Date.context_today(Mission)

# La condition de soumission exige au moins une competence recherchee.
Competence = env['opex.innovation.competence'].sudo()
competence = Competence.search([('code', '=', 'demo_ssi')], limit=1)
if not competence:
    competence = Competence.create({
        'name': "Securite des systemes d'information",
        'code': 'demo_ssi',
    })


def transition(record, code, user):
    definition = record.workflow_definition_id
    trans = definition.transition_ids.filtered(lambda t: t.code == code)
    record.with_user(user).sudo().workflow_do_transition(
        trans, comment="Etape franchie par le jeu de demonstration.")
    record.invalidate_recordset()


def new_mission(title, **overrides):
    values = {
        'title': title,
        'mission_type_id': mission_type.id,
        'client_id': client.partner_id.id,
        'description': "Besoin exprime par le client.",
        'objectifs': "Identifier et hierarchiser les vulnerabilites.",
        'domaine_id': domaine.id,
        'skill_ids': [(6, 0, competence.ids)],
        'date_limite_candidature': today + timedelta(days=30),
        'date_debut_souhaitee': today + timedelta(days=40),
        'date_fin_souhaitee': today + timedelta(days=60),
        'duree_estimee_jours': 15,
        'sourcing_mode': 'hybride',
    }
    values.update(overrides)
    return Mission.create(values)


def open_call(mission):
    transition(mission, 'mission_submit', client)
    transition(mission, 'mission_start_sourcing', manager)
    transition(mission, 'mission_open_applications', manager)
    return mission


def apply_for(mission):
    application = Application.create({
        'mission_id': mission.id,
        'partner_id': expert.partner_id.id,
    })
    transition(application, 'application_view', expert)
    transition(application, 'application_express_interest', expert)
    application.sudo().write({
        'disponibilite': 'oui',
        'delai_propose_jours': 10,
        'tarif_propose': 25000.0,
        'type_tarif': 'tjm',
        'motivation': "Quinze ans d'audit SI.",
        'methodologie': "Revue documentaire, entretiens, tests techniques.",
        'consentement': True,
    })
    transition(application, 'application_apply', expert)
    return application


def run_contract(mission):
    transition(mission, 'mission_start_contracting', secretariat)
    instance = mission.sudo()._contract_instance()
    for code in ('contract_submit_review', 'contract_send_to_sign'):
        trans = instance.definition_id.transition_ids.filtered(
            lambda t: t.code == code)
        actor = secretariat if code == 'contract_submit_review' else manager
        instance.with_user(actor).sudo().do_transition(trans, comment="Demo.")
    contract = mission.sudo().contract_id
    contract.action_sign_client()
    contract.action_sign_intervenant()
    mission.invalidate_recordset()
    for code in ('contract_sign', 'contract_validate'):
        trans = instance.definition_id.transition_ids.filtered(
            lambda t: t.code == code)
        actor = manager if code == 'contract_sign' else decideur
        instance.with_user(actor).sudo().do_transition(trans, comment="Demo.")
    mission.invalidate_recordset()


created = []

# 1. Une mission menee jusqu'au bout : alimente la colonne "Termine" et la
#    reputation de l'expert.
complete = new_mission("Audit cybersecurite - siege")
open_call(complete)
application = apply_for(complete)
transition(application, 'application_screen', manager)
transition(application, 'application_shortlist', manager)
transition(application, 'application_select', decideur)
transition(complete, 'mission_close_applications', manager)
transition(complete, 'mission_award', decideur)
run_contract(complete)
transition(complete, 'mission_start', manager)

# Un livrable en retard : colonne "Urgent" du §43.
Deliverable = env['opex.mission.deliverable'].sudo()
late = Deliverable.create({
    'mission_id': complete.id,
    'name': "Rapport de vulnerabilites",
    'deadline': today - timedelta(days=4),
})
late.write({'file': b'ZmljaGllcg==', 'filename': 'v1.pdf'})
created.append(('livrable en retard', late.display_name))

# 2. Une demande fraiche, en attente de qualification : colonne "A traiter".
pending = new_mission("Formation cybersecurite - equipes")
transition(pending, 'mission_submit', client)
created.append(('demande a qualifier', pending.name))

# 3. Un appel ouvert avec une candidature deposee : colonne "A traiter".
sourcing = new_mission("Conseil en continuite d'activite")
open_call(sourcing)
apply_for(sourcing)
created.append(('candidature deposee', sourcing.name))

env.cr.commit()

print("RESULTAT comptes: demo_client / demo_expert / demo_manager / "
      "demo_comite / demo_secretariat, mot de passe %s" % PASSWORD)
print("RESULTAT missions: %s (en cours), %s, %s"
      % (complete.name, pending.name, sourcing.name))
for label, value in created:
    print("RESULTAT %s: %s" % (label, value))
