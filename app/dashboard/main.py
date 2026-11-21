"""
Painel administrativo — FastAPI + endpoints REST.
Sirva o frontend React em /static ou use como API pura.
"""
import base64
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Depends, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from datetime import datetime, timedelta

from app.database.connection import get_db
from app.database.models import Product, Promotion, SentMessage, Click, Configuration
from app.core.config import settings
from app.core.env_writer import update_env_file
from app.core.bot_state import is_bot_enabled, set_bot_enabled, is_source_enabled, set_source_enabled
from app.whatsapp import bridge_process

SOURCES = ("mercadolivre", "shopee")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Sobe a bridge do WhatsApp junto com o painel (se local e ainda não estiver rodando).
    from app.whatsapp.evolution_client import EvolutionAPIClient

    if (settings.BRIDGE_AUTOSTART and bridge_process.is_local()
            and not (await EvolutionAPIClient().get_qr())["reachable"]):
        error = bridge_process.start()
        if error:
            from app.core.logger import get_logger
            get_logger("dashboard").warning(f"[WA] Bridge não iniciada: {error}")
    yield
    bridge_process.stop()


app = FastAPI(title="Robo-Promo Dashboard", version="1.0.0", lifespan=lifespan)

PUBLIC_PATHS = {"/health"}
# Front hospedado fora do robô (ex.: Vercel): manda o login no header Authorization.
ALLOWED_ORIGINS = {
    o.strip().rstrip("/") for o in settings.DASHBOARD_ALLOWED_ORIGINS.split(",") if o.strip()
}


@app.middleware("http")
async def require_login(request: Request, call_next):
    """
    Login HTTP Basic (o navegador mostra a janela de usuário/senha) quando
    DASHBOARD_PASSWORD está definido. Também recusa escrita vinda de outro site
    (CSRF): o navegador reenviaria a senha salva em um POST forjado.
    """
    origin = request.headers.get("origin")
    trusted_origin = origin in ALLOWED_ORIGINS
    if request.method not in ("GET", "HEAD", "OPTIONS") and not trusted_origin:
        # Sec-Fetch-Site vem do próprio navegador e não depende do Host reescrito
        # por proxy (Caddy/Tailscale). Sem ele (navegador antigo), compara Origin.
        fetch_site = request.headers.get("sec-fetch-site")
        hosts = {request.headers.get("host"), request.headers.get("x-forwarded-host")}
        if fetch_site:
            blocked = fetch_site not in ("same-origin", "none")
        else:
            blocked = bool(origin) and urlparse(origin).netloc not in hosts
        if blocked:
            return JSONResponse({"detail": "Origem não permitida"}, status_code=403)

    password = settings.DASHBOARD_PASSWORD
    if not password or request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        try:
            user, _, given = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
        except (ValueError, UnicodeDecodeError):
            user, given = "", ""
        user_ok = secrets.compare_digest(user.encode(), settings.DASHBOARD_USER.encode())
        pass_ok = secrets.compare_digest(given.encode(), password.encode())
        if user_ok and pass_ok:
            return await call_next(request)

    # Sem WWW-Authenticate para o front externo: ele tem tela de login própria
    # e o navegador não deve abrir a janela nativa de senha.
    headers = {} if trusted_origin else {"WWW-Authenticate": 'Basic realm="Robo-Promo", charset="UTF-8"'}
    return Response("Login necessário", status_code=401, headers=headers)


# Registrado depois do login => fica por fora: responde o preflight (OPTIONS)
# e põe os headers CORS inclusive nas respostas 401.
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
)


STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/admin", StaticFiles(directory=STATIC_DIR, html=True), name="admin")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/admin/")

# Campos editáveis pela tela de configuração, por app — adicione novos aqui.
SETTINGS_FIELDS: dict[str, dict[str, str]] = {
    "ml": {
        "app_id": "ML_APP_ID",
        "secret_key": "ML_SECRET_KEY",
        "affiliate_id": "ML_AFFILIATE_ID",
        "affiliate_tag": "ML_AFFILIATE_TAG",
    },
    "shopee": {
        "app_id": "SHOPEE_APP_ID",
        "secret_key": "SHOPEE_SECRET_KEY",
    },
    "whatsapp": {
        "api_url": "EVOLUTION_API_URL",
        "api_key": "EVOLUTION_API_KEY",
        "instance": "EVOLUTION_INSTANCE",
    },
}
SECRET_SUBKEYS = {"secret_key", "api_key"}

# Parâmetros globais de filtro/envio — tipados (não são segredos, só precisam
# do cast certo antes de ir pro objeto `settings`, já que PromotionFilter
# espera float/int/bool reais, não string).
FILTER_FIELDS: dict[str, tuple[str, type]] = {
    "min_discount_percent": ("MIN_DISCOUNT_PERCENT", float),
    "min_savings_brl": ("MIN_SAVINGS_BRL", float),
    "min_rating": ("MIN_RATING", float),
    "require_coupon": ("REQUIRE_COUPON", bool),
    "repost_cooldown_hours": ("REPOST_COOLDOWN_HOURS", int),
    "significant_price_drop_pct": ("SIGNIFICANT_PRICE_DROP_PCT", float),
    "max_promotions_per_cycle": ("MAX_PROMOTIONS_PER_CYCLE", int),
    "scraper_interval_seconds": ("SCRAPER_INTERVAL_SECONDS", int),
}


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "•" * len(value)
    return "•" * (len(value) - 4) + value[-4:]


@app.get("/api/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_products = (await db.execute(select(func.count(Product.id)))).scalar()
    total_sent = (await db.execute(select(func.count(SentMessage.id)))).scalar()
    total_clicks = (await db.execute(select(func.count(Click.id)))).scalar()

    last_24h = datetime.utcnow() - timedelta(hours=24)
    sent_today = (await db.execute(
        select(func.count(SentMessage.id)).where(SentMessage.sent_at >= last_24h)
    )).scalar()

    return {
        "total_products": total_products,
        "total_sent": total_sent,
        "total_clicks": total_clicks,
        "sent_today": sent_today,
    }


@app.get("/api/promotions")
async def list_promotions(
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Promotion, Product)
        .join(Product)
        .order_by(desc(Promotion.detected_at))
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": p.id,
            "product": prod.name,
            "original_price": float(p.original_price),
            "promotional_price": float(p.promotional_price),
            "discount_percent": float(p.discount_percent),
            "affiliate_url": p.affiliate_url,
            "detected_at": p.detected_at.isoformat(),
            "is_active": p.is_active,
        }
        for p, prod in rows
    ]


@app.get("/api/sent")
async def list_sent(
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(SentMessage, Promotion, Product)
        .join(Promotion)
        .join(Product)
        .order_by(desc(SentMessage.sent_at))
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": sm.id,
            "product": prod.name,
            "channel_id": sm.channel_id,
            "price_at_send": float(sm.price_at_send or 0),
            "sent_at": sm.sent_at.isoformat(),
            "status": sm.status,
        }
        for sm, p, prod in rows
    ]


@app.get("/api/config")
async def get_config(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Configuration))).scalars().all()
    return {r.key: r.value for r in rows}


@app.put("/api/config/{key}")
async def update_config(key: str, value: dict, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(Configuration).where(Configuration.key == key))).scalar_one_or_none()
    if row:
        row.value = value["value"]
    else:
        db.add(Configuration(key=key, value=value["value"]))
    await db.commit()
    return {"ok": True}


@app.get("/api/bot-status")
async def get_bot_status(db: AsyncSession = Depends(get_db)):
    return {"enabled": await is_bot_enabled(db)}


@app.put("/api/bot-status")
async def update_bot_status(body: dict, db: AsyncSession = Depends(get_db)):
    enabled = bool(body.get("enabled"))
    await set_bot_enabled(db, enabled)
    return {"ok": True, "enabled": enabled}


@app.get("/api/sources-status")
async def get_sources_status(db: AsyncSession = Depends(get_db)):
    return {source: await is_source_enabled(db, source) for source in SOURCES}


@app.put("/api/sources-status/{source}")
async def update_source_status(source: str, body: dict, db: AsyncSession = Depends(get_db)):
    if source not in SOURCES:
        raise HTTPException(status_code=404, detail=f"loja desconhecida: {source}")
    enabled = bool(body.get("enabled"))
    await set_source_enabled(db, source, enabled)
    return {"ok": True, "source": source, "enabled": enabled}


@app.get("/api/settings")
async def get_settings():
    """Valores atuais por app (ML/Shopee/WhatsApp). Segredos vêm mascarados — nunca em texto puro."""
    result = {}
    for app_name, fields in SETTINGS_FIELDS.items():
        result[app_name] = {}
        for subkey, env_key in fields.items():
            value = getattr(settings, env_key, "") or ""
            result[app_name][subkey] = _mask(value) if subkey in SECRET_SUBKEYS else value
            result[app_name][f"{subkey}_set"] = bool(value)

    # WHATSAPP_CHANNELS é lista de dict (JSON), não string — fora do loop genérico.
    channels = settings.WHATSAPP_CHANNELS
    result["whatsapp"]["channels"] = json.dumps(channels, ensure_ascii=False) if channels else ""
    result["whatsapp"]["channels_set"] = bool(channels)

    return result


@app.put("/api/settings")
async def update_settings(body: dict):
    """
    Corpo: { "ml": {"app_id": "...", "secret_key": "...", ...}, "shopee": {...}, "whatsapp": {...} }
    Campos omitidos ou vazios não são alterados (evita sobrescrever um segredo
    já salvo com a máscara que o front recebeu no GET).
    """
    updates: dict[str, str] = {}
    for app_name, fields in SETTINGS_FIELDS.items():
        payload = body.get(app_name) or {}
        for subkey, env_key in fields.items():
            value = payload.get(subkey)
            if value is None:
                continue
            value = str(value).strip()
            if not value:
                continue
            updates[env_key] = value
            setattr(settings, env_key, value)

    channels_raw = (body.get("whatsapp") or {}).get("channels")
    if channels_raw:
        try:
            parsed = json.loads(channels_raw)
            if not isinstance(parsed, list):
                raise ValueError("deve ser uma lista")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"WHATSAPP_CHANNELS inválido: {e}")
        settings.WHATSAPP_CHANNELS = parsed
        updates["WHATSAPP_CHANNELS"] = json.dumps(parsed, ensure_ascii=False)

    if updates:
        update_env_file(updates)

    # Bridge iniciada pelo painel usa porta/API key antigas — encerra; o próximo
    # GET /api/whatsapp/status sobe de novo com os valores novos.
    if {"EVOLUTION_API_URL", "EVOLUTION_API_KEY"} & updates.keys():
        bridge_process.stop()

    return {"ok": True, "updated": list(updates.keys())}


@app.get("/api/whatsapp/status")
async def whatsapp_status():
    """
    Estado do pareamento para a tela "Conectar WhatsApp" (o front consulta a cada poucos segundos).
    status: connected | qr | starting | offline | error. Se a bridge local estiver fora, tenta subir.
    """
    from app.whatsapp.evolution_client import EvolutionAPIClient

    info = await EvolutionAPIClient().get_qr()
    if not info["reachable"]:
        if bridge_process.is_starting():
            return {"status": "starting"}
        error = bridge_process.start()
        if error:
            return {"status": "offline", "error": error}
        return {"status": "starting"}
    if not info["auth_ok"]:
        return {"status": "error", "error": "A API Key do painel não confere com a da bridge (veja Avançado)."}
    if info["state"] == "open":
        return {"status": "connected"}
    if info["qr"]:
        return {"status": "qr", "qr": info["qr"]}
    return {"status": "starting"}


@app.post("/api/whatsapp/logout")
async def whatsapp_logout():
    """Desconecta o número atual; a bridge gera um QR Code novo para parear outro."""
    from app.whatsapp.evolution_client import EvolutionAPIClient

    if not await EvolutionAPIClient().logout():
        raise HTTPException(status_code=502, detail="Não foi possível desconectar — a bridge está rodando?")
    return {"ok": True}


@app.post("/api/whatsapp/test")
async def test_whatsapp():
    """Testa a conexão com a instância Evolution API configurada."""
    from app.whatsapp.evolution_client import EvolutionAPIClient

    connected = await EvolutionAPIClient().check_connection()
    return {"connected": connected}


@app.post("/api/whatsapp/send-test")
async def send_whatsapp_test():
    """Envia uma mensagem de texto de teste pra cada canal em WHATSAPP_CHANNELS."""
    from app.whatsapp.evolution_client import EvolutionAPIClient

    channels = settings.WHATSAPP_CHANNELS
    if not channels:
        raise HTTPException(status_code=400, detail="Nenhum canal configurado em WHATSAPP_CHANNELS")

    client = EvolutionAPIClient()
    text = f"🤖 Robo-Promo — mensagem de teste ({datetime.utcnow().strftime('%d/%m %H:%M UTC')})"
    results = []
    for channel in channels:
        channel_id = channel.get("id", "")
        sent = await client.send_text(channel_id, text)
        results.append({"channel_id": channel_id, "sent": sent})

    return {"results": results}


@app.get("/api/whatsapp/groups")
async def list_whatsapp_groups():
    """Lista grupos do WhatsApp conectado (via whatsapp-bridge) para montar WHATSAPP_CHANNELS."""
    from app.whatsapp.evolution_client import EvolutionAPIClient

    groups = await EvolutionAPIClient().list_groups()
    return {"groups": groups}


@app.get("/api/filters")
async def get_filters():
    return {subkey: getattr(settings, env_key) for subkey, (env_key, _) in FILTER_FIELDS.items()}


@app.put("/api/filters")
async def update_filters(body: dict):
    """Corpo: { "min_discount_percent": 30, "require_coupon": false, ... } — campos omitidos não mudam."""
    updates: dict[str, str] = {}
    for subkey, (env_key, caster) in FILTER_FIELDS.items():
        if subkey not in body or body[subkey] is None or body[subkey] == "":
            continue
        try:
            value = bool(body[subkey]) if caster is bool else caster(body[subkey])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{env_key} inválido")
        setattr(settings, env_key, value)
        updates[env_key] = str(value).lower() if caster is bool else str(value)

    if updates:
        update_env_file(updates)

    return {"ok": True, "updated": list(updates.keys())}


@app.post("/api/trigger")
async def trigger_now():
    """Dispara um ciclo imediato fora do schedule."""
    from app.scheduler.tasks import check_promotions
    check_promotions.delay()
    return {"message": "Ciclo iniciado"}


@app.post("/api/ml/setup-token")
async def setup_ml_token(body: dict, db: AsyncSession = Depends(get_db)):
    """
    Salva o refresh_token inicial após o primeiro fluxo OAuth.
    Corpo: { "refresh_token": "TG-XXXXXX", "access_token": "APP_USR-XXXXX" }
    Depois disso o sistema renova automaticamente.
    """
    from app.database.models import Configuration
    from datetime import timedelta

    for key in ("refresh_token", "access_token"):
        value = body.get(key)
        if not value:
            continue
        db_key = f"ml_{key}"
        row = (await db.execute(
            select(Configuration).where(Configuration.key == db_key)
        )).scalar_one_or_none()
        if row:
            row.value = value
        else:
            db.add(Configuration(key=db_key, value=value, description=f"ML {key}"))

    # Marca expiração daqui a 6h para forçar renovação na próxima chamada
    expires_at = (datetime.utcnow() + timedelta(hours=6)).isoformat()
    row = (await db.execute(
        select(Configuration).where(Configuration.key == "ml_token_expires_at")
    )).scalar_one_or_none()
    if row:
        row.value = expires_at
    else:
        db.add(Configuration(key="ml_token_expires_at", value=expires_at))

    await db.commit()
    return {"ok": True, "message": "Tokens salvos. Renovação automática ativada."}


@app.get("/api/ml/token-status")
async def ml_token_status(db: AsyncSession = Depends(get_db)):
    """Mostra quando o token atual expira."""
    from app.database.models import Configuration
    row = (await db.execute(
        select(Configuration).where(Configuration.key == "ml_token_expires_at")
    )).scalar_one_or_none()
    if not row:
        return {"status": "não configurado"}
    expires_at = datetime.fromisoformat(str(row.value))
    remaining = (expires_at - datetime.utcnow()).total_seconds()
    return {
        "expires_at": str(row.value),
        "remaining_seconds": max(0, int(remaining)),
        "status": "válido" if remaining > 0 else "expirado",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
