"""La mission vue depuis son service fait et sa facturation — §27 à §29.

POURQUOI LE SCHÉMA 12 N'EST PAS UNE CINQUIÈME DÉFINITION DE WORKFLOW

Le Schéma 12 du §29 donne le cycle de la facturation :

    Mission validée → Facturation → Facture générée → En attente de paiement
    → Payée

Quatre cases, et la tentation est claire : une définition de plus, et le module
en compterait cinq. C'est un piège, et c'est le même que celui des jalons de
l'Extension 8 — avec une aggravation.

Ces quatre cases **existent déjà**, et pas dans notre module : ce sont
`sale.order.state`, `sale.order.invoice_status` et `account.move.payment_state`.
Odoo les tient, les met à jour au rythme des écritures comptables, et n'a besoin
de personne pour le faire. Une définition parallèle serait un second récit de la
même histoire, et elle se désynchroniserait au premier paiement enregistré
depuis l'écran de banque — c'est-à-dire par le chemin normal.

La ligne de partage du CLAUDE.md du moteur s'applique telle quelle : le
constat de service fait a un valideur, un chemin de contestation et une boucle
de reprise — c'est un **processus**, il a sa définition. La facturation, chez
nous, est un **constat de ce qu'Odoo a fait** : on la lit, on ne la pilote pas.

Ce qui reste à notre charge tient en une action configurée sur
`mission_close` — « Facturer et clôturer », dont l'Extension 1 annonçait déjà
que « l'Extension 9 y rattachera la création du `sale.order` ».
"""

import logging

from markupsafe import Markup

from odoo import _, api, fields, models

from .optional_backends import SALE_ORDER

_logger = logging.getLogger(__name__)

ACCEPTANCE_WORKFLOW_CODE = 'mission_service_acceptance'
SERVICE_PRODUCT = 'opex_intervenants.product_mission_service'

#: Les positions du Schéma 12, telles que l'utilisateur les lit. Le modèle
#: n'invente rien : chacune correspond à un fait vérifiable dans `sale.order`
#: ou `account.move`.
#: La cinquième position, qui n'est pas du Schéma 12 : elle dit que le module
#: de facturation n'est pas là. Voir `_invoicing_label()` — la confondre avec
#: « Non facturée » enverrait chercher une commande qui n'a jamais pu exister.
INVOICING_UNAVAILABLE = "Facturation indisponible (module Ventes absent)"
INVOICING_NOT_STARTED = "Non facturée"
INVOICING_ORDERED = "Facturation en cours"
INVOICING_AWAITING_PAYMENT = "En attente de paiement"
INVOICING_PAID = "Payée"

#: `account.move.payment_state` — les valeurs qui valent « l'argent est arrivé ».
#: `in_payment` en fait partie : le règlement est enregistré, il attend le
#: rapprochement bancaire. L'exclure ferait afficher « En attente de paiement »
#: à un client qui a déjà payé.
PAID_STATES = ('paid', 'in_payment')


class MissionRequestInvoicing(models.Model):
    """§27 à §29 — le service fait, la facturation et le suivi du paiement.

    Les champs ajoutés ici sont des **faits**, jamais un avancement. Même
    parti qu'à l'Extension 7 sur les faits contractuels : un fait se constate
    par lecture, un état se décide par une transition. Aucun de ces champs ne
    se pose — tous se recalculent.
    """

    _inherit = 'opex.mission.request'

    acceptance_ids = fields.One2many(
        'opex.service.acceptance', 'mission_id',
        string="Constat de service fait")
    acceptance_id = fields.Many2one(
        'opex.service.acceptance',
        string="Constat en cours",
        compute='_compute_service_facts',
        help="Créé par le déclencheur de « Soumettre les livrables ».",
    )
    acceptance_stage_label = fields.Char(
        string="Service fait",
        compute='_compute_service_facts',
        help="L'étape du constat, telle que l'utilisateur la lit. Vide tant "
             "que la mission n'a pas atteint la remise des livrables.",
    )

    #: **Le champ que lit la condition de « Valider le service fait ».**
    #:
    #: Non stocké, contrairement aux deux compteurs de livrables de
    #: l'Extension 8 — et la différence se justifie. Ceux-là sont stockés parce
    #: que les tableaux de bord du §42 les filtrent et les agrègent
    #: (« Livrables à valider : 5 »). Celui-ci n'est filtré par personne : il
    #: n'est lu qu'au moment où le moteur évalue la condition, et un calcul
    #: frais y vaut mieux qu'une valeur à resynchroniser.
    service_fait_valide = fields.Boolean(
        string="Service fait validé",
        compute='_compute_service_facts',
        help="Le constat du §28 a été validé par le cluster puis par le "
             "client. Lu par la condition de « Valider le service fait ».",
    )

    # --- Le Schéma 12, en lecture ------------------------------------------
    #
    # REBRANCHEMENT `sale` — ce champ était :
    #
    #     sale_order_id = fields.Many2one(
    #         'sale.order', string="Commande de facturation",
    #         compute='_compute_service_facts')
    #
    # Remplacé par le libellé seul. Non stocké comme les huit autres, donc
    # aucune donnée à migrer : le jour où `sale` revient, on rétablit la
    # `Many2one` et `_compute_service_facts()` la repose au premier calcul.
    sale_order_name = fields.Char(
        string="Commande de facturation",
        compute='_compute_service_facts',
    )
    facturation_disponible = fields.Boolean(
        string="Facturation disponible",
        compute='_compute_service_facts',
        help="Faux tant que le module Ventes n'est pas installé. Les blocs "
             "de facturation des écrans s'y réfèrent plutôt que d'afficher "
             "des montants à zéro qui laisseraient croire à un impayé.",
    )
    facture_generee = fields.Boolean(
        string="Facture générée", compute='_compute_service_facts')
    facture_payee = fields.Boolean(
        string="Facture payée", compute='_compute_service_facts')
    montant_facture = fields.Monetary(
        string="Montant facturé", currency_field='currency_id',
        compute='_compute_service_facts')
    montant_restant_du = fields.Monetary(
        string="Reste à payer", currency_field='currency_id',
        compute='_compute_service_facts')
    facturation_label = fields.Char(
        string="Situation de facturation",
        compute='_compute_service_facts',
        help="La position du Schéma 12 du §29, lue dans la commande et les "
             "factures — jamais décidée par ce module.",
    )

    # ------------------------------------------------------------
    # Les faits
    # ------------------------------------------------------------
    #
    # Une seule méthode, neuf champs, **tous non stockés**. Le registre
    # refuse qu'une même méthode produise du stocké et du non stocké
    # (`registry.py:543`, règle 9). Ici il n'y a pas de mélange, et aucun de
    # ces neuf champs ne doit être stocké : `facture_payee` figé par un
    # `store=True` continuerait d'affirmer qu'une facture est réglée après un
    # avoir.

    # REBRANCHEMENT `sale` — la chaîne complète était :
    #
    #     @api.depends(
    #         'acceptance_ids.workflow_stage_id',
    #         'acceptance_ids.sale_order_id.invoice_ids.payment_state',
    #         'acceptance_ids.sale_order_id.invoice_ids.amount_total',
    #         'acceptance_ids.sale_order_id.invoice_ids.amount_residual',
    #     )
    #
    # Une dépendance qui traverse un champ inexistant fait échouer le montage
    # du registre, et le message ne nomme pas toujours le champ fautif. Les
    # trois branches supprimées sont celles qui rendaient `facture_payee`
    # vivant : un règlement saisi depuis l'écran de banque recalculait la
    # mission. Sans `sale`, il n'y a rien à recalculer — mais **le jour du
    # rebranchement, ces trois lignes sont indispensables**, sans quoi la
    # mission afficherait « En attente de paiement » sur une facture réglée
    # jusqu'au prochain recalcul, c'est-à-dire à un moment quelconque.
    @api.depends(
        'acceptance_ids.workflow_stage_id',
        'acceptance_ids.sale_order_ref',
    )
    def _compute_service_facts(self):
        backend = self.env['opex.optional.backend']
        available = backend._backend_available(SALE_ORDER)

        for mission in self:
            acceptance = mission.sudo().acceptance_ids[:1]
            order = backend._backend_record(
                SALE_ORDER, acceptance.sale_order_ref) if acceptance else None
            # `order` vaut None quand `sale` est absent, et un recordset vide
            # quand il est là mais qu'aucune commande n'a été émise. Les deux
            # se lisent pareil ici ; c'est plus bas, sur `facturation_label`,
            # que la distinction compte.
            invoices = order.invoice_ids.filtered(
                lambda move: move.move_type == 'out_invoice'
                and move.state != 'cancel') if order else None

            mission.acceptance_id = acceptance
            mission.acceptance_stage_label = \
                acceptance.workflow_stage_id.user_label or ''
            mission.service_fait_valide = bool(acceptance.is_accepted)

            mission.facturation_disponible = available
            mission.sale_order_name = acceptance.sale_order_name or ''
            mission.facture_generee = bool(invoices)
            mission.facture_payee = bool(invoices) and all(
                move.payment_state in PAID_STATES for move in invoices)
            mission.montant_facture = sum(
                invoices.mapped('amount_total')) if invoices else 0.0
            mission.montant_restant_du = sum(
                invoices.mapped('amount_residual')) if invoices else 0.0
            mission.facturation_label = mission._invoicing_label(
                available, order, invoices, mission.facture_payee)

    @staticmethod
    def _invoicing_label(available, order, invoices, paid):
        """La position du Schéma 12, déduite et jamais stockée.

        Le premier cas est nouveau, et il compte : **« Non facturée » et
        « facturation indisponible » ne veulent pas dire la même chose.** La
        première phrase décrit une mission qu'on n'a pas encore facturée ; la
        seconde décrit un portail qui ne sait pas facturer. Les confondre
        ferait chercher une commande manquante là où c'est le module qui
        l'est, et ce sont deux enquêtes différentes.
        """
        if not available:
            return INVOICING_UNAVAILABLE
        if not order:
            return INVOICING_NOT_STARTED
        if not invoices:
            return INVOICING_ORDERED
        return INVOICING_PAID if paid else INVOICING_AWAITING_PAYMENT

    # ------------------------------------------------------------
    # Les déclencheurs
    # ------------------------------------------------------------
    #
    # `selection_add` et non une seconde déclaration : les deux valeurs de
    # l'Extension 7 restent définies à un seul endroit. Les redéclarer ici
    # aurait produit deux listes à tenir d'accord, et c'est la copie périmée
    # qu'on aurait lue.
    #
    # Pas d'`ondelete` : le champ n'est pas stocké — il n'a aucune ligne en base
    # dont il faudrait décider du sort.

    operational_trigger = fields.Selection(
        selection_add=[
            ('service_acceptance', "Ouverture du constat de service fait"),
            ('invoicing', "Facturation de la mission"),
        ],
    )

    def _trigger_service_acceptance(self):
        """§27 — le constat naît à la remise des livrables.

        Placé sur « Soumettre les livrables » et non sur « Valider le service
        fait » : le constat est ce qui **instruit** la validation, il doit
        exister avant qu'elle soit prononcée. Posé sur la transition qui le
        conclut, il serait créé déjà validé et les deux passages du §28 —
        cluster puis client — n'auraient nulle part où se dérouler.

        Idempotent : la boucle de correction du §25 repasse par cette
        transition, et une mission n'a qu'un constat.
        """
        self.ensure_one()
        return self._ensure_acceptance()

    def _ensure_acceptance(self):
        """Le constat de la mission, créé une fois pour toutes."""
        self.ensure_one()
        Acceptance = self.env['opex.service.acceptance'].sudo()
        existing = Acceptance.search([('mission_id', '=', self.id)], limit=1)
        if existing:
            return existing

        assignments = self.sudo().assignment_ids.filtered('active')
        return Acceptance.create({
            'mission_id': self.id,
            'assignment_ids': [fields.Command.set(assignments.ids)],
            'currency_id': self.currency_id.id or False,
            # Le montant convenu, additionné sur les affectations actives : un
            # type de mission à plusieurs intervenants (l'exception de la
            # règle 4) produit une seule facture au client.
            'montant_a_facturer': sum(assignments.mapped('montant_total')),
        })

    def _trigger_invoicing(self):
        """§29 — la commande de vente et la facture, à la clôture.

        Rattaché à « Facturer et clôturer », comme l'Extension 1 l'avait
        annoncé sur cette transition. Le nom de la transition dit déjà
        l'arbitrage du CLAUDE.md : « INVOICED du document UX est ici : la
        facturation est une **action** portée par cette transition, pas une
        étape. »

        **Tout se passe dans un savepoint, et c'est la règle 10.** Une
        écriture comptable qui échoue — journal manquant, compte de produit non
        paramétré, exercice clos — laisse la transaction PostgreSQL en état
        abandonné : *tout* ce qui suit reçoit « current transaction is
        aborted », y compris l'enregistrement de la transition qu'on est en
        train de franchir. Un `try/except` seul n'y changerait rien.

        Le parti est donc : ou la facturation aboutit entièrement, ou elle est
        annulée et **signalée** dans le dossier. Une mission clôturée sans
        facture est un problème visible ; une transaction morte est un 500.
        """
        self.ensure_one()
        acceptance = self.sudo().acceptance_ids[:1]
        if not acceptance:
            _logger.info(
                "opex_intervenants: mission %s clôturée sans constat de "
                "service fait ; aucune facturation déclenchée.", self.id)
            return False

        # REBRANCHEMENT `sale` — le garde-fou d'installation.
        #
        # Il est ici et pas plus bas, et l'endroit compte : la transition
        # « Facturer et clôturer » doit **aboutir** même sans le module. Une
        # mission qu'on ne peut plus clôturer parce que la comptabilité
        # manque serait bloquée pour une raison qui ne la regarde pas.
        #
        # Ce que le §29 perd est donc la commande et la facture, pas la
        # clôture. Et le dossier le dit : la note ci-dessous est la seule
        # trace qu'aura le gestionnaire, elle nomme le module et dit quoi
        # faire à la main.
        Backend = self.env['opex.optional.backend']
        if not Backend._backend_available(SALE_ORDER):
            _logger.info(
                "opex_intervenants: mission %s clôturée sans facturation ; "
                "le module Ventes n'est pas installé.", self.id)
            self.sudo().message_post(
                # `Markup` : `message_post()` **échappe** un body `str`, et
                # les balises s'affichent alors telles quelles dans le fil -
                # `&lt;p&gt;` sous les yeux du lecteur. Mesuré sur cette base.
                #
                # Le défaut était présent sur les trois notes du module qui
                # portent du balisage ; les trois sont corrigées. Les deux
                # notes de signature de `mission_contract.py` restent en `str`,
                # et c'est juste : elles ne contiennent aucune balise, et
                # l'échappement y protège un nom d'intervenant.
                body=Markup(_(
                    "<p>La mission est clôturée. <strong>Aucune commande de "
                    "vente n'a été émise</strong> : le module %(module)s "
                    "n'est pas installé sur cette instance.</p>"
                    "<p>Montant à facturer au client : <strong>%(amount)s"
                    "</strong>. La facturation est à établir hors du portail, "
                    "puis à reporter sur le constat de service fait.</p>"
                )) % {
                    'module': Backend._backend_missing_note(SALE_ORDER),
                    'amount': acceptance.montant_a_facturer,
                },
                subtype_xmlid='mail.mt_note',
            )
            return False

        if acceptance.sale_order_ref:
            return Backend._backend_record(
                SALE_ORDER, acceptance.sale_order_ref)

        try:
            with self.env.cr.savepoint():
                order = self._create_sale_order(acceptance)
                order.action_confirm()
                order._create_invoices()
                acceptance.write({
                    'sale_order_ref': order.id,
                    'sale_order_name': order.name,
                })
        except Exception as error:  # noqa: BLE001 — voir la docstring
            # Le rollback du savepoint défait les écritures en base, pas le
            # cache de l'ORM, qui contiendrait alors une commande jamais
            # écrite. Règle 10, second temps.
            self.env.invalidate_all()
            _logger.warning(
                "opex_intervenants: facturation de la mission %s impossible : "
                "%s", self.id, error)
            self.sudo().message_post(
                # `Markup` : `message_post()` **échappe** un body `str`, et
                # les balises s'affichent alors telles quelles dans le fil -
                # `&lt;p&gt;` sous les yeux du lecteur. Mesuré sur cette base.
                #
                # Le défaut était présent sur les trois notes du module qui
                # portent du balisage ; les trois sont corrigées. Les deux
                # notes de signature de `mission_contract.py` restent en `str`,
                # et c'est juste : elles ne contiennent aucune balise, et
                # l'échappement y protège un nom d'intervenant.
                body=Markup(_(
                    "<p>La facturation automatique n'a pas abouti : "
                    "<em>%s</em></p><p>La mission est clôturée ; la commande "
                    "de vente est à établir manuellement depuis les Ventes, "
                    "puis à rattacher au constat de service fait.</p>"
                )) % error,
                subtype_xmlid='mail.mt_note',
            )
            return False

        self.sudo().message_post(
            # `Markup`, comme la note d'indisponibilité ci-dessus : sans lui
            # les balises s'affichent telles quelles dans le fil.
            body=Markup(_(
                "<p>Facturation émise : <strong>%(order)s</strong> pour "
                "%(amount)s.</p>"
            )) % {
                'order': acceptance.sale_order_name,
                'amount': acceptance.montant_a_facturer,
            },
            subtype_xmlid='mail.mt_note',
        )
        return Backend._backend_record(SALE_ORDER, acceptance.sale_order_ref)

    def _service_product(self):
        """Le produit de service du §29, créé au premier besoin.

        REBRANCHEMENT `sale` — il était semé par
        `data/mission_invoicing_data.xml`, retiré parce qu'il portait
        `invoice_policy`, un champ de `sale`, et parce que `product.product`
        vient d'un module que le manifeste ne déclare plus. Voir le
        commentaire conservé dans ce fichier de données.

        Il reçoit le même identifiant externe qu'auparavant : une base qui
        aura tourné sans `sale` puis avec retrouvera un seul produit, pas
        deux.

        Attention : `invoice_policy = 'order'` : en `'delivery'`, `_create_invoices()`
        refuserait de facturer une quantité livrée nulle, et la facturation
        échouerait sur chaque mission.
        """
        product = self.env.ref(SERVICE_PRODUCT, raise_if_not_found=False)
        if product:
            return product

        module, name = SERVICE_PRODUCT.split('.')
        product = self.env['product.product'].sudo().create({
            'name': "Prestation de mission OPEX",
            'type': 'service',
            'invoice_policy': 'order',
            'list_price': 0.0,
            'purchase_ok': False,
        })
        self.env['ir.model.data'].sudo().create({
            'module': module,
            'name': name,
            'model': 'product.product',
            'res_id': product.id,
            'noupdate': True,
        })
        return product

    def _create_sale_order(self, acceptance):
        """La commande du §29, dont le document donne le contenu attendu.

        > « Les informations peuvent reprendre automatiquement : client,
        >   intervenant, référence de mission, montant, prestations, date. »

        Les six y sont : le client est le partenaire de la commande,
        l'intervenant et la référence sont dans le libellé de la ligne, le
        montant est celui du constat, la prestation est le produit de service,
        et la date est celle de la commande.
        """
        self.ensure_one()
        mission = self.sudo()
        product = self._service_product()

        intervenants = ", ".join(
            assignment.partner_id.display_name
            for assignment in acceptance.assignment_ids
        ) or _("intervenant non renseigné")

        # Atteignable seulement quand `sale` est installé : `_trigger_invoicing()`
        # s'arrête avant. `self.env[...]` plutôt que le pont, volontairement —
        # cette méthode est le code de la fonctionnalité, pas sa garde, et elle
        # doit rester lisible telle qu'elle sera rebranchée.
        return self.env[SALE_ORDER].sudo().create({
            'partner_id': mission.client_id.id,
            'client_order_ref': mission.name,
            'origin': mission.name,
            'order_line': [fields.Command.create({
                'product_id': product.id,
                'name': _(
                    "%(reference)s — %(title)s\nIntervenant(s) : %(experts)s"
                ) % {
                    'reference': mission.name,
                    'title': mission.title or '',
                    'experts': intervenants,
                },
                'product_uom_qty': 1.0,
                'price_unit': acceptance.montant_a_facturer,
            })],
        })

    # ------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------

    def action_open_acceptance_workflow(self):
        """Ouvre le wizard de transition du **constat**, pas de la mission.

        Le bouton « Action » de la fiche fait avancer la mission ; le constat
        de service fait est un autre processus sur un autre enregistrement, et
        il a le sien. Même précaution qu'à l'Extension 7 avec la
        contractualisation : deux boutons nommés pour qu'on ne les confonde
        pas.
        """
        self.ensure_one()
        acceptance = self.sudo().acceptance_ids[:1]
        if not acceptance:
            return False
        return acceptance.workflow_instance_id.action_open_transition_wizard()

    def action_view_acceptance(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Constat de service fait"),
            'res_model': 'opex.service.acceptance',
            'view_mode': 'form',
            'res_id': self.sudo().acceptance_ids[:1].id,
        }
