from odoo.tests.common import TransactionCase


class WorkflowCase(TransactionCase):
    """Socle des tests du moteur.

    Le modèle piloté par les workflows de test est **`res.partner`**, un
    modèle natif d'Odoo que le moteur n'a jamais vu.

    Ce n'est pas un raccourci de test, c'est la démonstration : si le moteur
    fait avancer un contact d'étape en étape, en évaluant des conditions sur ses
    champs natifs (`color`, `is_company`, `comment`), c'est qu'il ne doit rien
    à un modèle métier particulier. Un modèle jouet défini pour les tests
    prouverait beaucoup moins.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.Definition = cls.env['opex.workflow.definition']
        cls.Stage = cls.env['opex.workflow.stage']
        cls.Transition = cls.env['opex.workflow.transition']
        cls.Rule = cls.env['opex.workflow.rule']
        cls.Role = cls.env['opex.workflow.role']
        cls.Instance = cls.env['opex.workflow.instance']
        cls.History = cls.env['opex.workflow.history']

        cls.partner_model = cls.env['ir.model']._get('res.partner')

    # Les fabriques sont des `classmethod` : elles servent aussi bien depuis un
    # test que depuis `setUpClass`, où seul le niveau classe est disponible.

    @classmethod
    def _definition(cls, code="test_wf", name="Workflow de test", model=None):
        return cls.Definition.create({
            'name': name,
            'code': code,
            'model_id': (model or cls.partner_model).id,
        })

    @classmethod
    def _stage(cls, definition, code, name=None, is_start=False, is_end=False,
               sequence=10, user_label=None):
        return cls.Stage.create({
            'definition_id': definition.id,
            'code': code,
            'name': name or code.replace('_', ' ').capitalize(),
            'user_label': user_label or False,
            'is_start': is_start,
            'is_end': is_end,
            'sequence': sequence,
        })

    @classmethod
    def _transition(cls, definition, code, source, target, name=None,
                    roles=None, conditions=None, requires_comment=False):
        return cls.Transition.create({
            'definition_id': definition.id,
            'code': code,
            'name': name or code.replace('_', ' ').capitalize(),
            'source_stage_id': source.id,
            'target_stage_id': target.id,
            'allowed_role_ids': [(6, 0, roles.ids)] if roles else False,
            'condition_ids': [(6, 0, conditions.ids)] if conditions else False,
            'requires_comment': requires_comment,
        })

    @classmethod
    def _rule(cls, code, expression, message="Condition non remplie.", name=None):
        return cls.Rule.create({
            'name': name or code,
            'code': code,
            'expression': expression,
            'message': message,
        })

    @classmethod
    def _linear_definition(cls, code="linear_wf", publish=True):
        """Brouillon → Contrôle → Clôturé, plus un refus depuis le contrôle.

        Deux sorties depuis « Contrôle » : c'est le cas minimal qui interdit de
        supposer qu'une étape n'a qu'une transition sortante.
        """
        definition = cls._definition(code=code)
        draft = cls._stage(definition, 'draft', "Brouillon",
                           is_start=True, sequence=10,
                           user_label="Compléter mon dossier")
        review = cls._stage(definition, 'review', "Contrôle", sequence=20,
                            user_label="Contrôle en cours")
        done = cls._stage(definition, 'done', "Clôturé", is_end=True, sequence=30,
                          user_label="Dossier clôturé")
        rejected = cls._stage(definition, 'rejected', "Refusé", is_end=True,
                              sequence=40, user_label="Dossier refusé")

        cls._transition(definition, 'submit', draft, review, "Soumettre")
        cls._transition(definition, 'validate', review, done, "Valider")
        cls._transition(definition, 'reject', review, rejected, "Refuser",
                        requires_comment=True)

        if publish:
            definition.action_publish()
        return definition
