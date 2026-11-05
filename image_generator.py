"""Integração opcional com uma instância local do ComfyUI."""
from __future__ import annotations

import ipaddress
import re
import threading
import time
from functools import wraps
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import requests
from resource_manager import serialize_gpu_task


class ImageGenerationError(RuntimeError):
    pass


# O ComfyUI compartilha VRAM entre geração, edição e upscale. Uma trava global
# impede que duas ações da Gac.IA submetam workflows pesados ao mesmo tempo.
_COMFY_JOB_LOCK = threading.RLock()


def serializar_trabalho_comfyui(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with _COMFY_JOB_LOCK:
            return func(*args, **kwargs)
    return wrapper


def _verificar_recursos_gpu_para_imagem(*, reuse_loaded_model: bool = False) -> None:
    """Não inicia nova carga pesada quando a GPU NVIDIA já está sob pressão."""
    try:
        from resource_manager import get_gpu_status, image_gpu_decision
        status = get_gpu_status(refresh=True)
        permitido, motivo = image_gpu_decision(status, reuse_loaded_model=reuse_loaded_model)
    except Exception as erro:
        # A proteção nunca deve travar PCs sem sensores NVIDIA.
        raise ImageGenerationError(f"Não consegui validar os recursos locais da GPU: {erro}") from erro
    if not permitido:
        raise ImageGenerationError(motivo)


def _detalhe_http(response) -> str:
    """Extrai diagnóstico limitado sem despejar respostas enormes no chat/log."""
    try:
        dados = response.json()
        detalhe = str(dados)
    except (ValueError, TypeError):
        detalhe = str(getattr(response, "text", "") or "")
    detalhe = " ".join(detalhe.split())
    return detalhe[:1800] or "O servidor não forneceu detalhes."


def _validar_host_local(base_url: str) -> str:
    texto = str(base_url or "http://127.0.0.1:8188").strip().rstrip("/")
    partes = urlsplit(texto)
    if partes.scheme != "http" or not partes.hostname or partes.username or partes.password:
        raise ImageGenerationError("Use uma URL HTTP local do ComfyUI, como http://127.0.0.1:8188.")
    host = partes.hostname.lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if not local:
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = False
    if not local:
        raise ImageGenerationError("Por segurança, a primeira integração aceita apenas ComfyUI no próprio computador.")
    return texto


def fila_comfyui_ocupada(base_url: str, timeout: float = 5.0) -> bool:
    """Indica se há workflow em execução/espera; não interrompe trabalho externo."""
    base = _validar_host_local(base_url)
    try:
        response = requests.get(f"{base}/queue", timeout=timeout)
        response.raise_for_status()
        queue = response.json()
        if not isinstance(queue, dict):
            return True
        return bool(queue.get("queue_running") or queue.get("queue_pending"))
    except (requests.RequestException, ValueError, TypeError):
        # Sem conseguir verificar, tratamos a fila como ocupada e não liberamos
        # modelos que podem estar sendo usados por outra interface.
        return True


def liberar_memoria_comfyui(base_url: str, timeout: float = 8.0) -> tuple[bool, str]:
    """Descarrega modelos ociosos sem cancelar workflows de terceiros."""
    base = _validar_host_local(base_url)
    try:
        queue_response = requests.get(f"{base}/queue", timeout=min(timeout, 5.0))
        queue_response.raise_for_status()
        queue = queue_response.json()
        if not isinstance(queue, dict):
            return False, "Estado da fila do ComfyUI inválido; memória não foi liberada."
        if queue.get("queue_running") or queue.get("queue_pending"):
            return False, "ComfyUI possui workflows em execução ou na fila; memória não foi liberada."
        response = requests.post(
            f"{base}/free",
            json={"unload_models": True, "free_memory": True},
            timeout=timeout,
        )
        response.raise_for_status()
        return True, "Modelos ociosos do ComfyUI descarregados da VRAM."
    except requests.RequestException as exc:
        return False, f"ComfyUI indisponível ou sem resposta para liberar memória: {exc}"


def listar_checkpoints(base_url: str, timeout: float = 5.0) -> list[str]:
    base = _validar_host_local(base_url)
    try:
        response = requests.get(f"{base}/object_info/CheckpointLoaderSimple", timeout=timeout)
        response.raise_for_status()
        data = response.json()
        node = data.get("CheckpointLoaderSimple", {})
        required = node.get("input", {}).get("required", {})
        choices = required.get("ckpt_name", [[]])[0]
        return [str(item) for item in choices if isinstance(item, str)]
    except (requests.RequestException, ValueError, KeyError, TypeError) as erro:
        raise ImageGenerationError(f"Não foi possível consultar o ComfyUI: {erro}") from erro


def parametros_checkpoint(checkpoint: str) -> dict:
    """Presets de partida com balanço entre qualidade e latência em GPUs de 8–12 GB."""
    nome = str(checkpoint or "").casefold()
    if "dreamshaperxl_turbo" in nome or "dreamshaper-xl-turbo" in nome:
        return {"steps": 6, "cfg": 2.0, "sampler_name": "dpmpp_sde", "scheduler": "karras",
                "negative": "low quality, worst quality, bad anatomy, watermark"}
    if "animagine" in nome:
        return {"steps": 20, "cfg": 5.5, "sampler_name": "euler_ancestral", "scheduler": "normal",
                "negative": "lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, cropped, worst quality, low quality, signature, watermark, username, blurry",
                "prompt_suffix": "masterpiece, high score, great score, absurdres"}
    if "juggernaut" in nome:
        return {"steps": 20, "cfg": 5.0, "sampler_name": "dpmpp_2m", "scheduler": "karras", "negative": ""}
    if "realvis" in nome:
        return {"steps": 20, "cfg": 5.0, "sampler_name": "dpmpp_sde", "scheduler": "karras",
                "negative": "low quality, worst quality, illustration, painting, cartoon, blurry, watermark"}
    return {"steps": 18, "cfg": 6.0, "sampler_name": "dpmpp_2m", "scheduler": "karras",
            "negative": "low quality, blurry, distorted, watermark, text artifacts"}


@serialize_gpu_task
@serializar_trabalho_comfyui
def gerar_imagem(
    prompt: str,
    base_url: str,
    checkpoint: str,
    output_dir: str | Path,
    width: int = 768,
    height: int = 768,
    steps: int | None = None,
    timeout: int = 300,
    status_callback=None,
    negative_prompt: str = "",
    reuse_loaded_model: bool = False,
) -> Path:
    texto = str(prompt or "").strip()
    if not texto:
        raise ImageGenerationError("Descreva a imagem que deseja gerar.")
    if not checkpoint or not str(checkpoint).strip():
        raise ImageGenerationError("Selecione um checkpoint instalado no ComfyUI nas configurações do gerador.")
    base = _validar_host_local(base_url)
    _verificar_recursos_gpu_para_imagem(reuse_loaded_model=reuse_loaded_model)
    # Se a API não estiver ativa, tenta iniciar uma instalação portátil legada já existente.
    # Em instalações Desktop, o usuário inicia o ComfyUI pelo próprio aplicativo.
    # O gerador não instala executáveis nem baixa modelos/checkpoints automaticamente.
    try:
        from comfy_manager import garantir_comfyui_ativo
        garantir_comfyui_ativo(base, progress=status_callback)
    except ImportError:
        pass
    except Exception as erro:
        raise ImageGenerationError(str(erro)) from erro
    width = max(256, min(1536, int(width) // 64 * 64))
    height = max(256, min(1536, int(height) // 64 * 64))
    preset = parametros_checkpoint(str(checkpoint))
    try:
        passos_efetivos = preset["steps"] if steps is None else max(1, min(50, int(steps)))
    except (TypeError, ValueError):
        passos_efetivos = preset["steps"]
    prompt_efetivo = texto
    if preset.get("prompt_suffix") and preset["prompt_suffix"].casefold() not in texto.casefold():
        prompt_efetivo = f"{texto}, {preset['prompt_suffix']}"
    negative_text = ", ".join(part.strip() for part in (preset.get("negative", ""), str(negative_prompt or "")) if part.strip())
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": str(checkpoint)}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt_efetivo, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative_text, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": int(time.time_ns() % (2**32)), "steps": passos_efetivos, "cfg": preset["cfg"], "sampler_name": preset["sampler_name"], "scheduler": preset["scheduler"], "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "GacIA", "images": ["6", 0]}},
    }
    # Evita enviar workflow com checkpoint inexistente: a API fornece a lista
    # efetiva de modelos carregáveis pelo nó CheckpointLoaderSimple.
    checkpoints = listar_checkpoints(base)
    if str(checkpoint) not in checkpoints:
        exemplos = ", ".join(checkpoints[:8]) or "nenhum checkpoint detectado"
        raise ImageGenerationError(
            f"Checkpoint '{checkpoint}' não encontrado no ComfyUI. Disponíveis: {exemplos}."
        )

    client_id = str(uuid.uuid4())
    try:
        if status_callback:
            status_callback("Enviando imagem ao ComfyUI...")
        response = requests.post(f"{base}/prompt", json={"prompt": workflow, "client_id": client_id}, timeout=20)
        if response.status_code >= 400:
            raise ImageGenerationError(
                f"ComfyUI rejeitou o workflow (HTTP {response.status_code}): {_detalhe_http(response)}"
            )
        try:
            resposta_prompt = response.json()
        except ValueError as erro:
            raise ImageGenerationError("ComfyUI retornou uma resposta inválida ao receber o workflow.") from erro
        if not isinstance(resposta_prompt, dict):
            raise ImageGenerationError("ComfyUI retornou um formato inesperado ao receber o workflow.")
        prompt_id = resposta_prompt.get("prompt_id")
        if not prompt_id:
            raise ImageGenerationError("O ComfyUI não retornou um identificador de geração.")

        deadline = time.monotonic() + max(30, min(int(timeout), 900))
        history = None
        while time.monotonic() < deadline:
            time.sleep(1.5)
            if status_callback:
                status_callback("Gerando imagem... aguarde a GPU concluir.")
            check = requests.get(f"{base}/history/{prompt_id}", timeout=10)
            if check.status_code >= 400:
                raise ImageGenerationError(
                    f"Falha ao consultar o histórico do ComfyUI (HTTP {check.status_code}): {_detalhe_http(check)}"
                )
            data = check.json()
            history = data.get(prompt_id)
            if history and history.get("outputs"):
                break
            status = (history or {}).get("status", {})
            if status.get("status_str") == "error" or status.get("completed") is False and status.get("messages"):
                raise ImageGenerationError("O ComfyUI informou uma falha no workflow. Verifique o console dele.")
        if not history or not history.get("outputs"):
            raise ImageGenerationError("Tempo limite excedido aguardando o ComfyUI.")

        image_info = None
        for output in history.get("outputs", {}).values():
            images = output.get("images", []) if isinstance(output, dict) else []
            if images:
                image_info = images[0]
                break
        if not image_info:
            raise ImageGenerationError("A execução terminou, mas não retornou uma imagem.")
        params = {key: str(image_info.get(key, "")) for key in ("filename", "subfolder", "type")}
        image_response = requests.get(f"{base}/view", params=params, timeout=30)
        image_response.raise_for_status()
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        safe_prompt = re.sub(r"[^A-Za-z0-9_-]+", "_", texto[:35]).strip("_") or "imagem"
        destination = folder / f"{safe_prompt}_{prompt_id[:8]}.png"
        destination.write_bytes(image_response.content)
        return destination
    except requests.RequestException as erro:
        response = getattr(erro, "response", None)
        if response is not None:
            detalhe = _detalhe_http(response)
            raise ImageGenerationError(
                f"Falha na comunicação com o ComfyUI (HTTP {response.status_code}): {detalhe}"
            ) from erro
        raise ImageGenerationError(f"Falha na comunicação com o ComfyUI: {erro}") from erro


def listar_modelos_upscale(base_url: str, timeout: float = 8.0) -> list[str]:
    """Retorna somente os modelos que o nó oficial UpscaleModelLoader expõe."""
    base = _validar_host_local(base_url)
    try:
        response = requests.get(f"{base}/object_info/UpscaleModelLoader", timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        node = payload.get("UpscaleModelLoader", {}) if isinstance(payload, dict) else {}
        required = node.get("input", {}).get("required", {})
        choices = required.get("model_name", [[]])[0]
        if not isinstance(choices, (list, tuple)):
            return []
        return [str(item) for item in choices if isinstance(item, str) and item.strip()]
    except (requests.RequestException, ValueError, KeyError, TypeError) as erro:
        raise ImageGenerationError(f"Não foi possível consultar os modelos de upscale do ComfyUI: {erro}") from erro


@serializar_trabalho_comfyui
def upscale_image(
    input_path: str | Path,
    output_dir: str | Path,
    base_url: str = "http://127.0.0.1:8188",
    model_name: str = "",
    timeout: int = 600,
    status_callback=None,
) -> Path:
    """Executa super-resolução por modelo neural já instalado no ComfyUI local.

    O tamanho final depende do modelo (por exemplo, um modelo 4x). A Gac.IA não
    baixa modelos automaticamente nem substitui super-resolução por interpolação.
    """
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise ImageGenerationError("A imagem de origem não existe ou não é um arquivo.")
    if source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
        raise ImageGenerationError("Formato de imagem não suportado. Use PNG, JPG, WEBP, BMP ou TIFF.")
    if source.stat().st_size > 100 * 1024 * 1024:
        raise ImageGenerationError("A imagem excede o limite de 100 MB para envio ao ComfyUI.")
    _verificar_recursos_gpu_para_imagem()
    try:
        from PIL import Image
        with Image.open(source) as image:
            width, height = image.size
            image.verify()
        if width < 1 or height < 1 or width * height > 64_000_000:
            raise ImageGenerationError("A imagem precisa ter dimensões válidas e no máximo 64 megapixels.")
    except ImportError as erro:
        raise ImageGenerationError("Pillow não está disponível; execute preparar.bat para validar a imagem.") from erro
    except ImageGenerationError:
        raise
    except Exception as erro:
        raise ImageGenerationError(f"A imagem está inválida ou corrompida: {erro}") from erro

    base = _validar_host_local(base_url)
    try:
        from comfy_manager import garantir_comfyui_ativo
        garantir_comfyui_ativo(base, progress=status_callback)
    except ImportError:
        pass
    except Exception as erro:
        raise ImageGenerationError(str(erro)) from erro

    modelos = listar_modelos_upscale(base)
    if not modelos:
        raise ImageGenerationError(
            "Nenhum modelo de upscale foi encontrado em ComfyUI/models/upscale_models. "
            "Adicione um modelo compatível (por exemplo, 4x-UltraSharp ou RealESRGAN_x4plus) e tente novamente."
        )
    solicitado = str(model_name or "").strip()
    if solicitado and solicitado not in modelos:
        raise ImageGenerationError(
            f"Modelo de upscale '{solicitado}' não encontrado. Disponíveis: {', '.join(modelos[:12])}."
        )
    if not solicitado:
        preferencias = ("4x-ultrasharp", "realesrgan_x4plus", "4x_nmkd-siax_200k")
        solicitado = next(
            (modelo for preferencia in preferencias for modelo in modelos if preferencia in modelo.lower()),
            modelos[0],
        )

    client_id = str(uuid.uuid4())
    try:
        if status_callback:
            status_callback("Enviando imagem para o ComfyUI...")
        with source.open("rb") as stream:
            upload = requests.post(
                f"{base}/upload/image",
                files={"image": (source.name, stream, "application/octet-stream")},
                data={"type": "input", "overwrite": "true"},
                timeout=(10, 120),
            )
        if upload.status_code >= 400:
            raise ImageGenerationError(
                f"ComfyUI recusou o envio da imagem (HTTP {upload.status_code}): {_detalhe_http(upload)}"
            )
        uploaded = upload.json()
        uploaded_name = uploaded.get("name") if isinstance(uploaded, dict) else None
        if not isinstance(uploaded_name, str) or not uploaded_name:
            raise ImageGenerationError("ComfyUI não retornou o nome da imagem enviada.")

        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {"image": uploaded_name}},
            "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": solicitado}},
            "3": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
            "4": {"class_type": "SaveImage", "inputs": {"filename_prefix": "GacIA_Upscale", "images": ["3", 0]}},
        }
        if status_callback:
            status_callback(f"Aplicando super-resolução com {solicitado}...")
        response = requests.post(
            f"{base}/prompt", json={"prompt": workflow, "client_id": client_id}, timeout=30,
        )
        if response.status_code >= 400:
            raise ImageGenerationError(
                f"ComfyUI rejeitou o upscale (HTTP {response.status_code}): {_detalhe_http(response)}"
            )
        prompt_data = response.json()
        prompt_id = prompt_data.get("prompt_id") if isinstance(prompt_data, dict) else None
        if not prompt_id:
            node_errors = prompt_data.get("node_errors") if isinstance(prompt_data, dict) else None
            raise ImageGenerationError(f"ComfyUI não aceitou o fluxo de upscale. {str(node_errors or '')[:1200]}")

        deadline = time.monotonic() + max(30, min(int(timeout), 1800))
        history = None
        while time.monotonic() < deadline:
            time.sleep(1.5)
            check = requests.get(f"{base}/history/{prompt_id}", timeout=10)
            if check.status_code >= 400:
                raise ImageGenerationError(
                    f"Falha ao consultar o upscale (HTTP {check.status_code}): {_detalhe_http(check)}"
                )
            payload = check.json()
            history = payload.get(prompt_id) if isinstance(payload, dict) else None
            if history and history.get("outputs"):
                break
            status = (history or {}).get("status", {})
            if status.get("status_str") == "error":
                raise ImageGenerationError("O ComfyUI falhou ao executar o modelo de upscale. Verifique o console dele.")
            if status_callback:
                status_callback("Aguardando o modelo neural concluir a super-resolução...")
        if not history or not history.get("outputs"):
            raise ImageGenerationError("Tempo limite excedido aguardando o upscale no ComfyUI.")

        image_info = None
        for output in history.get("outputs", {}).values():
            images = output.get("images", []) if isinstance(output, dict) else []
            if images:
                image_info = images[0]
                break
        if not image_info:
            raise ImageGenerationError("O ComfyUI concluiu, mas não retornou o arquivo de imagem.")
        params = {key: str(image_info.get(key, "")) for key in ("filename", "subfolder", "type")}
        result = requests.get(f"{base}/view", params=params, timeout=(10, 120))
        if result.status_code >= 400:
            raise ImageGenerationError(
                f"Não foi possível baixar o resultado (HTTP {result.status_code}): {_detalhe_http(result)}"
            )
        if not result.content or len(result.content) > 150 * 1024 * 1024:
            raise ImageGenerationError("O arquivo de saída está vazio ou ultrapassa 150 MB.")
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / f"{source.stem}_upscaled_{prompt_id[:8]}.png"
        if destination.exists():
            destination = folder / f"{source.stem}_upscaled_{uuid.uuid4().hex[:8]}.png"
        destination.write_bytes(result.content)
        try:
            with Image.open(destination) as check_image:
                check_image.verify()
        except Exception as erro:
            destination.unlink(missing_ok=True)
            raise ImageGenerationError(f"O resultado do ComfyUI não é uma imagem válida: {erro}") from erro
        return destination
    except ImageGenerationError:
        raise
    except requests.RequestException as erro:
        response = getattr(erro, "response", None)
        if response is not None:
            raise ImageGenerationError(
                f"Falha de comunicação com o ComfyUI (HTTP {response.status_code}): {_detalhe_http(response)}"
            ) from erro
        raise ImageGenerationError(f"Falha de comunicação com o ComfyUI: {erro}") from erro
    except (ValueError, TypeError) as erro:
        raise ImageGenerationError(f"ComfyUI retornou uma resposta inesperada: {erro}") from erro
