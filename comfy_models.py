"""Gerenciamento seguro de modelos locais do ComfyUI e catálogo Hugging Face.

Downloads são iniciados somente por ação explícita do usuário, usam HTTPS,
metadados do Hugging Face, arquivo temporário e validação de tamanho/hash.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import time
from typing import Callable
from urllib.parse import quote

import requests

BASE_DIR = Path(__file__).resolve().parent
CATALOGO = {
    "juggernaut-xl-v9": {
        "name": "Juggernaut XL v9", "category": "photorealistic",
        "description": "Fotografia, retratos e realismo cinematográfico.",
        "repo": "RunDiffusion/Juggernaut-XL-v9",
        "file": "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors",
        "license": "CreativeML Open RAIL-M; serviços de API pagos exigem autorização/licença específica do autor.",
        "min_vram_gb": 8, "estimated_gb": 7.11,
    },
    "dreamshaper-xl-turbo": {
        "name": "DreamShaper XL Turbo", "category": "artistic",
        "description": "Ilustração, arte estilizada e geração mais rápida.",
        "repo": "Lykon/dreamshaper-xl-turbo",
        "file": "DreamShaperXL_Turbo_SFWdpmppSde_half_pruned.safetensors",
        "license": "Hugging Face indica openrail++; consulte o texto completo da licença e os termos do autor antes de uso comercial.",
        "min_vram_gb": 8, "estimated_gb": 6.94,
    },
    "animagine-xl-4-opt": {
        "name": "Animagine XL 4.0 Opt", "category": "anime",
        "description": "Anime e mangá; versão otimizada da família Animagine XL.",
        "repo": "cagliostrolab/animagine-xl-4.0",
        "file": "animagine-xl-4.0-opt.safetensors",
        "license": "CreativeML Open RAIL++-M; consulte as condições de uso do modelo.",
        "min_vram_gb": 8, "estimated_gb": 6.94,
    },
    "realvis-xl-v5": {
        "name": "RealVisXL V5.0 FP16", "category": "photorealistic",
        "description": "Fotografia realista e retratos; variante FP16.",
        "repo": "SG161222/RealVisXL_V5.0",
        "file": "RealVisXL_V5.0_fp16.safetensors",
        "license": "CreativeML Open RAIL++; consulte as condições de uso do modelo.",
        "min_vram_gb": 8, "estimated_gb": 6.94,
    },
}

MODEL_FOLDERS = {
    "checkpoints": "checkpoints", "loras": "loras", "vae": "vae",
    "controlnet": "controlnet", "upscale_models": "upscale_models",
    "embeddings": "embeddings", "clip_vision": "clip_vision",
    "text_encoders": "text_encoders", "diffusion_models": "diffusion_models",
}


class ComfyModelError(RuntimeError):
    pass


def obter_catalogo(info_hardware: dict | None = None) -> list[dict]:
    gpus = (info_hardware or {}).get("gpus") or []
    gpu = next((item for item in gpus if item.get("vendor") in {"NVIDIA", "AMD", "Intel"}), {})
    vram_free = gpu.get("vram_free_mb")
    vram_total = gpu.get("vram_mb")
    vram_gb = float(vram_free) / 1024 if vram_free is not None and float(vram_free) > 0 else None
    total_gb = float(vram_total) / 1024 if vram_total is not None and float(vram_total) > 0 else None
    resultado = []
    for model_id, item in CATALOGO.items():
        clone = {"id": model_id, **item}
        # Nunca marque o checkpoint como recomendado usando apenas a VRAM total.
        clone["recommended"] = bool(vram_gb is not None and vram_gb >= item["min_vram_gb"])
        clone["hardware_note"] = (
            "VRAM livre não foi identificada; a VRAM total informada não garante espaço disponível. Confira os requisitos antes de baixar."
            if vram_gb is None and total_gb is not None else
            "VRAM não foi identificada; confira os requisitos antes de baixar."
            if vram_gb is None else
            "VRAM livre abaixo da recomendação; pode exigir offload/tiling e demorar mais."
            if vram_gb < item["min_vram_gb"] else ""
        )
        resultado.append(clone)
    return resultado


def detectar_raiz_comfy(caminho: str | Path | None = None) -> Path | None:
    candidatos: list[Path] = []
    if caminho:
        candidatos.append(Path(caminho).expanduser())
    env = os.environ.get("GACIA_COMFY_DIR") or os.environ.get("COMFYUI_DIR")
    if env:
        candidatos.append(Path(env).expanduser())
    try:
        cfg = json.loads((BASE_DIR / "config.json").read_text(encoding="utf-8"))
        saved = cfg.get("gerador_imagens", {}).get("comfy_model_dir")
        if saved:
            candidatos.append(Path(saved).expanduser())
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    candidatos.extend([
        BASE_DIR / "runtime" / "ComfyUI",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "ComfyUI",
        Path(os.environ.get("APPDATA", "")) / "ComfyUI",
    ])
    for candidato in candidatos:
        try:
            raiz = candidato.resolve()
            if (raiz / "models").is_dir():
                return raiz
            # O usuário pode apontar diretamente à pasta models.
            if raiz.name.lower() == "models" and raiz.is_dir():
                return raiz.parent
        except OSError:
            continue
    return None


def diretorio_modelos(raiz: str | Path, categoria: str) -> Path:
    if categoria not in MODEL_FOLDERS:
        raise ComfyModelError(f"Categoria de modelo inválida: {categoria}")
    base = Path(raiz).expanduser().resolve()
    if base.name.lower() == "models":
        modelos = base
    else:
        modelos = base / "models"
    destino = (modelos / MODEL_FOLDERS[categoria]).resolve()
    try:
        destino.relative_to(modelos.resolve())
    except ValueError as erro:
        raise ComfyModelError("O caminho de destino saiu da pasta models do ComfyUI.") from erro
    return destino


def listar_modelos_instalados(raiz: str | Path, categorias: list[str] | None = None) -> dict[str, list[dict]]:
    resultado = {}
    for categoria in categorias or list(MODEL_FOLDERS):
        if categoria not in MODEL_FOLDERS:
            continue
        pasta = diretorio_modelos(raiz, categoria)
        arquivos = []
        if pasta.is_dir():
            for arquivo in sorted(pasta.iterdir(), key=lambda p: p.name.casefold()):
                try:
                    if arquivo.is_file() and not arquivo.is_symlink() and arquivo.suffix.lower() in {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".onnx"}:
                        arquivos.append({"name": arquivo.name, "size_bytes": arquivo.stat().st_size, "path": str(arquivo)})
                except OSError:
                    continue
        resultado[categoria] = arquivos
    return resultado


def _metadados_hf(repo: str, filename: str, timeout: tuple[float, float] = (5, 20)) -> dict:
    if (not isinstance(repo, str) or len(repo) > 200
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repo)):
        raise ComfyModelError("Repositório Hugging Face inválido; use organização/nome-do-repositório.")
    if (not isinstance(filename, str) or len(filename) > 255
            or not filename.lower().endswith(".safetensors")
            or filename.startswith(("/", "\\")) or ".." in Path(filename).parts
            or "/" in filename or "\\" in filename or any(ord(c) < 32 for c in filename)):
        raise ComfyModelError("Por segurança, o gerenciador baixa somente arquivos .safetensors sem caminhos relativos.")
    url = f"https://huggingface.co/api/models/{quote(repo, safe='/')}?blobs=true"
    try:
        response = requests.get(url, timeout=timeout, headers={"User-Agent": "GacIA-ModelManager/1.0"})
        if response.status_code != 200:
            raise ComfyModelError(f"Hugging Face respondeu HTTP {response.status_code} ao consultar o modelo.")
        data = response.json()
    except (requests.RequestException, ValueError) as erro:
        raise ComfyModelError(f"Não foi possível consultar os metadados do modelo: {erro}") from erro
    siblings = data.get("siblings") if isinstance(data, dict) else None
    for sibling in siblings or []:
        if sibling.get("rfilename") == filename:
            lfs = sibling.get("lfs") or {}
            size = lfs.get("size") or sibling.get("size")
            sha256 = lfs.get("sha256")
            try:
                size = int(size) if size is not None else None
            except (TypeError, ValueError):
                size = None
            if size is not None and (size < 1024 * 1024 or size > 25 * 1024 ** 3):
                raise ComfyModelError("Tamanho do arquivo fora do limite de segurança (1 MiB a 25 GiB).")
            if sha256 and (len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256.lower())):
                sha256 = None
            return {"size": size, "sha256": sha256, "url": f"https://huggingface.co/{quote(repo, safe='/')}/resolve/main/{quote(filename, safe='/')}"}
    raise ComfyModelError(f"O arquivo {filename} não foi encontrado no repositório {repo}. O catálogo pode estar desatualizado.")


def baixar_modelo_hf(
    repo: str,
    filename: str,
    categoria: str,
    raiz_comfy: str | Path,
    *,
    progress: Callable[[str], None] | None = None,
    cancel_event=None,
    overwrite: bool = False,
) -> Path:
    """Baixa um safetensors de um repositório Hugging Face informado pelo usuário.

    O destino é sempre uma pasta de modelo permitida do ComfyUI; o nome de arquivo
    nunca pode conter caminho. O download exige ação explícita, espaço livre, tamanho
    e SHA-256 quando fornecidos pelo Hugging Face.
    """
    if categoria not in MODEL_FOLDERS:
        raise ComfyModelError(f"Categoria de modelo inválida: {categoria}")
    if not isinstance(filename, str) or Path(filename).name != filename or filename in {".", ".."}:
        raise ComfyModelError("Informe apenas o nome do arquivo, sem pastas.")
    pasta = diretorio_modelos(raiz_comfy, categoria)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / filename
    if destino.exists() and not overwrite:
        raise ComfyModelError(f"O modelo já existe: {destino.name}. Nada foi sobrescrito.")
    meta = _metadados_hf(repo, filename)
    if meta["size"] is None:
        raise ComfyModelError("O servidor não informou o tamanho do modelo; download cancelado por segurança.")
    livre = shutil.disk_usage(pasta).free
    if livre < meta["size"] + 256 * 1024 ** 2:
        raise ComfyModelError(
            f"Espaço insuficiente: o arquivo ocupa aproximadamente {meta['size'] / 1024**3:.2f} GiB; "
            f"há {livre / 1024**3:.2f} GiB livres."
        )
    temporario = destino.with_name(destino.name + ".part")
    existente = temporario.stat().st_size if temporario.exists() else 0
    hasher = hashlib.sha256() if meta["sha256"] else None
    if hasher and existente:
        with temporario.open("rb") as stream:
            for bloco in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                hasher.update(bloco)
    headers = {"User-Agent": "GacIA-ModelManager/1.0", "Accept-Encoding": "identity"}
    if existente:
        headers["Range"] = f"bytes={existente}-"
    try:
        with requests.get(meta["url"], headers=headers, stream=True, timeout=(10, 90), allow_redirects=True) as response:
            if existente and response.status_code == 200:
                existente = 0
                if hasher:
                    hasher = hashlib.sha256()
            elif existente and response.status_code != 206:
                raise ComfyModelError(f"Servidor não aceitou retomada do download (HTTP {response.status_code}).")
            elif not existente and response.status_code != 200:
                raise ComfyModelError(f"Download recusado pelo servidor (HTTP {response.status_code}).")
            content_range = response.headers.get("Content-Range", "")
            if existente and not content_range.startswith(f"bytes {existente}-"):
                raise ComfyModelError("Resposta de retomada não corresponde ao trecho solicitado.")
            modo = "ab" if existente else "wb"
            recebido = existente
            ultimo_update = 0.0
            with temporario.open(modo) as output:
                if not existente and hasher is None and meta["sha256"]:
                    hasher = hashlib.sha256()
                for bloco in response.iter_content(chunk_size=1024 * 1024):
                    if cancel_event is not None and cancel_event.is_set():
                        raise ComfyModelError("Download cancelado pelo usuário; o arquivo parcial foi preservado para retomada.")
                    if not bloco:
                        continue
                    output.write(bloco)
                    if hasher:
                        hasher.update(bloco)
                    recebido += len(bloco)
                    agora = time.monotonic()
                    if progress and (agora - ultimo_update > 0.4 or recebido >= meta["size"]):
                        pct = min(100, recebido / meta["size"] * 100)
                        progress(f"Baixando {filename}: {pct:.1f}% ({recebido / 1024**3:.2f}/{meta['size'] / 1024**3:.2f} GiB)")
                        ultimo_update = agora
                output.flush()
                os.fsync(output.fileno())
        if temporario.stat().st_size != meta["size"]:
            raise ComfyModelError("Download incompleto; arquivo parcial preservado para retomada.")
        if meta["sha256"] and hasher and hasher.hexdigest().lower() != meta["sha256"].lower():
            temporario.unlink(missing_ok=True)
            raise ComfyModelError("A verificação SHA-256 falhou. O arquivo parcial inválido foi removido.")
        if destino.exists():
            if not overwrite:
                raise ComfyModelError("O arquivo de destino surgiu durante o download; nada foi sobrescrito.")
            # O modelo antigo só sai do caminho depois que o novo foi baixado,
            # teve tamanho/hash validados e está pronto para promoção atômica.
            backup = destino.with_name(destino.name + ".bak")
            indice_backup = 1
            while backup.exists():
                backup = destino.with_name(destino.name + f".bak.{indice_backup}")
                indice_backup += 1
            os.replace(destino, backup)
            try:
                os.replace(temporario, destino)
            except Exception:
                os.replace(backup, destino)
                raise
            if progress:
                progress(f"Versão anterior preservada em {backup.name}.")
        else:
            os.replace(temporario, destino)
        if progress:
            progress(f"Modelo instalado e validado: {destino.name} → models/{categoria}/")
        return destino
    except requests.RequestException as erro:
        raise ComfyModelError(f"Falha de rede durante o download. O arquivo parcial pode ser retomado: {erro}") from erro


def baixar_modelo_catalogo(
    model_id: str,
    raiz_comfy: str | Path,
    *,
    progress: Callable[[str], None] | None = None,
    cancel_event=None,
    overwrite: bool = False,
) -> Path:
    """Baixa um checkpoint do catálogo de estilos, sem sobrescrever por padrão."""
    item = CATALOGO.get(str(model_id))
    if not item:
        raise ComfyModelError("Modelo não reconhecido no catálogo da Gac.IA.")
    return baixar_modelo_hf(
        item["repo"], item["file"], "checkpoints", raiz_comfy,
        progress=progress, cancel_event=cancel_event, overwrite=overwrite,
    )


def remover_modelo_instalado(raiz_comfy: str | Path, categoria: str, filename: str) -> dict:
    """Remove somente um arquivo-modelo regular da pasta gerenciada do ComfyUI."""
    if categoria not in MODEL_FOLDERS:
        raise ComfyModelError(f"Categoria de modelo inválida: {categoria}")
    if (not isinstance(filename, str) or not filename or len(filename) > 255
            or Path(filename).name != filename or "/" in filename or "\\" in filename
            or filename in {".", ".."}):
        raise ComfyModelError("Selecione um nome de arquivo sem caminhos.")
    pasta = diretorio_modelos(raiz_comfy, categoria).resolve()
    alvo = pasta / filename
    if alvo.is_symlink():
        raise ComfyModelError("Links simbólicos não podem ser removidos pelo gerenciador.")
    try:
        resolvido = alvo.resolve(strict=True)
        info = alvo.stat(follow_symlinks=False)
    except OSError as erro:
        raise ComfyModelError(f"Modelo não encontrado ou inacessível: {filename}") from erro
    if resolvido.parent != pasta or not alvo.is_file() or not filename.lower().endswith((".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".onnx")):
        raise ComfyModelError("O arquivo selecionado não é um modelo regular dentro da pasta permitida.")
    alvo.unlink()
    return {"name": filename, "category": categoria, "size_bytes": info.st_size}


def selecionar_checkpoint_preferido(checkpoints: list[str], preferred_style: str = "photorealistic") -> str:
    """Escolhe um checkpoint instalado coerente com o estilo salvo pelo usuário."""
    disponiveis = {str(item).casefold(): str(item) for item in checkpoints or []}
    estilos = {
        "photorealistic": ["juggernaut-xl-v9", "realvis-xl-v5", "dreamshaper-xl-turbo", "animagine-xl-4-opt"],
        "artistic": ["dreamshaper-xl-turbo", "juggernaut-xl-v9", "realvis-xl-v5", "animagine-xl-4-opt"],
        "anime": ["animagine-xl-4-opt", "dreamshaper-xl-turbo", "juggernaut-xl-v9", "realvis-xl-v5"],
        "versatile": ["juggernaut-xl-v9", "dreamshaper-xl-turbo", "realvis-xl-v5", "animagine-xl-4-opt"],
    }
    for model_id in estilos.get(str(preferred_style).lower(), estilos["photorealistic"]):
        filename = CATALOGO[model_id]["file"].casefold()
        if filename in disponiveis:
            return disponiveis[filename]
    return sorted(disponiveis.values(), key=str.casefold)[0] if disponiveis else ""


def listar_modelos_api(base_url: str = "http://127.0.0.1:8188", timeout: float = 5) -> dict[str, list[str]]:
    """Usa os endpoints de inventário experimental do ComfyUI quando disponíveis."""
    from comfy_manager import validar_url_comfy_local, ComfyManagerError
    base = validar_url_comfy_local(base_url)
    try:
        response = requests.get(base + "/api/experiment/models", timeout=timeout)
        if response.status_code != 200:
            raise ComfyModelError(f"API do ComfyUI não disponibiliza inventário avançado (HTTP {response.status_code}).")
        payload = response.json()
        folders = payload.get("folders", payload) if isinstance(payload, dict) else payload
        if not isinstance(folders, list):
            raise ComfyModelError("Resposta inesperada do endpoint de modelos do ComfyUI.")
        resultado = {}
        for entry in folders:
            nome = entry.get("name") if isinstance(entry, dict) else entry
            if nome not in MODEL_FOLDERS:
                continue
            modelos = requests.get(base + f"/api/experiment/models/{quote(nome)}", timeout=timeout)
            if modelos.status_code == 200:
                dados = modelos.json()
                resultado[nome] = [str(item.get("name") or item.get("filename") or item) for item in dados if isinstance(item, (str, dict))]
        return resultado
    except (requests.RequestException, ValueError) as erro:
        raise ComfyModelError(f"Não foi possível consultar os modelos do ComfyUI: {erro}") from erro
