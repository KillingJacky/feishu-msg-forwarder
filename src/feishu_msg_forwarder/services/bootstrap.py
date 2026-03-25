from __future__ import annotations

from ..auth.token_resolver import TokenManager
from ..config import load_config
from ..db.repositories import Repository
from ..db.sqlite import connect
from ..feishu.base_client import BaseFeishuClient
from ..feishu.media_api import MediaApi
from ..feishu.message_api import MessageApi
from ..feishu.search_api import SearchApi
from .forwarder import Forwarder
from .ingestor import Ingestor
from .poller import Poller


def build_runtime(config_file: str | None = None) -> Poller:
    config = load_config(config_file)
    conn = connect(config.db_path)
    repo = Repository(conn)
    
    token_manager = TokenManager(config)
    
    base_client = BaseFeishuClient(config.base_url, token_manager=token_manager)
    message_api = MessageApi(base_client)
    media_api = MediaApi(base_client)
    search_api = SearchApi(base_client)
    
    ingestor = Ingestor(repo, config.rules)
    forwarder = Forwarder(repo, message_api, media_api, token_manager)
    return Poller(config, repo, ingestor, forwarder, message_api, search_api, token_manager)
