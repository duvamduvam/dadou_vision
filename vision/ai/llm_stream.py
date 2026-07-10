"""Cerveau conversationnel streamé — appel LLM (via OpenRouter) + historique.

QUOI : contrairement à vision.ai.interactions (GPT-4o, réponse complète
      d'un coup, TTS déclenché APRÈS la réponse entière), ce module streame
      les deltas au fil de l'eau — c'est ce qui permet à vision.ai.
      conversation de faire parler le TTS dès la première phrase complète
      reçue, sans attendre la fin de la génération (cf. vision.ai.
      stream_parser).
POURQUOI OpenRouter plutôt que l'API OpenAI directe : base_url configurable
      (client OpenAI officiel, compatible — OpenRouter expose une API Chat
      Completions compatible OpenAI) permet de choisir le modèle par sa
      chaîne complète (ex: "anthropic/claude-haiku-4.5", cf.
      vision_config.py) sans changer de client SDK.
POURQUOI l'import openai est DIFFÉRÉ (dans _get_client, pas en tête de
      module) : même raison que vision.ai.tts_piper/stt — openai N'EST PAS
      dans requirements-test.txt (cf. tts.py/interactions.py existants, déjà
      logés hors CI pour la même raison), un import en tête de module
      casserait la collecte pytest en CI.
POURQUOI client_factory injectable : permet aux tests de fournir un faux
      client (deltas scriptés) SANS jamais importer openai ni appeler
      get_secret — le constructeur reste utilisable sans conf/secret sur la
      machine tant qu'un client_factory est fourni (chargement du secret
      PARESSEUX, seulement si le vrai client OpenAI doit être construit).
"""
from __future__ import annotations

from typing import Iterator

from vision.db.chat_db import ChatDB
from vision.vision_config import get_secret


class StreamingBrain:
    """Orchestration d'une conversation LLM streamée, historique persistant
    via ChatDB (réutilisé tel quel — cf. vision.db.chat_db)."""

    def __init__(self, model: str, base_url: str, api_key_name: str = "openrouter_key",
                 system_prompt: str = "", history_limit: int = 12, max_tokens: int = 200,
                 client_factory=None):
        self._model = model
        self._base_url = base_url
        self._api_key_name = api_key_name
        self._system_prompt = system_prompt
        self._history_limit = history_limit
        self._max_tokens = max_tokens
        self._client_factory = client_factory
        self._client = None  # créé PARESSEUSEMENT, cf. _get_client

        # Une session ChatDB par instance de StreamingBrain — même pattern
        # que vision.ai.interactions.AInteractions (ChatDB.create({}) au
        # constructeur, historique accumulé au fil des tours via
        # add_user_text/add_system_text).
        self._history_entry = ChatDB.create({})

    def _get_client(self):
        """Construit le client OpenAI (SDK officiel, pointé vers OpenRouter
        via base_url) au premier besoin réel — jamais au constructeur, pour
        que StreamingBrain reste instanciable sans conf/secret quand un
        client_factory est fourni (tests)."""
        if self._client is not None:
            return self._client

        if self._client_factory is not None:
            self._client = self._client_factory()
        else:
            from openai import OpenAI  # import différé, cf. docstring de module

            api_key = get_secret(self._api_key_name)
            self._client = OpenAI(base_url=self._base_url, api_key=api_key)
        return self._client

    def stream_reply(self, user_text: str) -> Iterator[str]:
        """Envoie `user_text` au LLM, streame les deltas de la réponse, et
        met à jour l'historique (ChatDB) : le message utilisateur est ajouté
        AVANT l'appel (il doit faire partie du contexte envoyé), la réponse
        complète est ajoutée APRÈS le streaming (une fois tous les deltas
        connus — on ne peut pas persister un historique partiel de façon
        cohérente si le flux est interrompu en cours de route, cf. gestion
        d'erreur dans vision.ai.conversation qui logge et abandonne le tour
        proprement)."""
        client = self._get_client()

        self._history_entry.add_user_text(user_text)

        # history_limit : ne renvoyer que les N derniers messages au LLM —
        # limite le coût/latence par requête (l'historique complet croît sans
        # borne sur une longue session, cf. config["chat_*"] pour la valeur
        # par défaut retenue).
        history = self._history_entry.get_history()[-self._history_limit:]
        messages = [{"role": "system", "content": self._system_prompt}] + history

        stream = client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=self._max_tokens,
            stream=True,
        )

        full_text = ""
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if not delta:
                # Un chunk de streaming peut ne porter aucun texte (métadonnées
                # de fin, chunk de rôle...) — rien à yield ni à accumuler.
                continue
            full_text += delta
            yield delta

        self._history_entry.add_system_text(full_text)
