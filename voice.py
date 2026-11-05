"""Motor de voz da Gac.IA com carregamento tardio das dependências pesadas."""
from __future__ import annotations

import asyncio
import gc
import logging
import os
import queue
import re
import tempfile
import threading
from collections import deque
from typing import Callable, Optional
from resource_manager import serialize_gpu_task

LOGGER = logging.getLogger("GacIA.Voz")


class GerenciadorVoz:
    """Gerencia Edge TTS, reprodução e transcrição local com Faster-Whisper.

    Nenhuma biblioteca nativa de áudio/IA é importada no construtor. Elas são
    carregadas somente quando o usuário aciona voz ou microfone.
    """

    def __init__(
        self,
        modelo_whisper: str = "small",
        device_preferido: str = "auto",
        language: str = "pt-BR",
    ):
        self.language = "en" if str(language).lower().startswith("en") else "pt"
        if self.language == "en":
            self.voz_feminina = "en-US-AriaNeural"
            self.voz_masculina = "en-US-GuyNeural"
        else:
            self.voz_feminina = "pt-BR-FranciscaNeural"
            self.voz_masculina = "pt-BR-AntonioNeural"
        self.modelo_whisper_nome = str(modelo_whisper or "small")
        self.device_preferido = device_preferido if device_preferido in {"auto", "cuda", "cpu"} else "auto"

        self.modelo_whisper = None
        self.whisper_device = "não carregado"
        self.whisper_compute_type = None

        self.falando = False
        self.ouvindo = False
        self._lock = threading.RLock()
        self._tts_lock = threading.Lock()
        self._tts_cancel = threading.Event()
        self._active_tts_cancel = self._tts_cancel
        self._sapi_engine = None
        self._sapi_cancel_event = None
        self._temp_file: Optional[str] = None

        self._escuta_thread: Optional[threading.Thread] = None
        self._escuta_stop = threading.Event()
        self._audio_stream = None
        self._audio_queue: queue.Queue = queue.Queue(maxsize=24)
        self.microfone_silenciado = False

        self._np = None
        self._sd = None
        self._WhisperModel = None
        self._pygame = None

    @staticmethod
    def limpar_texto_voz(texto: str) -> str:
        """Remove marcação Markdown e evita narrar blocos de código inteiros."""
        texto = str(texto or "")
        texto = re.sub(r"```.*?```", " Trecho de código omitido. ", texto, flags=re.DOTALL)
        texto = re.sub(r"```[^\n]*", "", texto)
        texto = re.sub(r"`([^`]+)`", r"\1", texto)
        texto = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", texto)
        texto = re.sub(r"\[([^\]]+)\]\((?:https?://)?[^)]+\)", r"\1", texto)
        texto = re.sub(r"https?://\S+", "", texto)
        texto = re.sub(r"^\s{0,3}#{1,6}\s+", "", texto, flags=re.MULTILINE)
        texto = re.sub(r"^\s*(?:[-*+] |\d+[.)] )", "", texto, flags=re.MULTILINE)
        texto = re.sub(r"(\*\*|__)(.*?)\1", r"\2", texto, flags=re.DOTALL)
        texto = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", texto)
        texto = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", texto)
        texto = re.sub(r"~~(.*?)~~", r"\1", texto)
        texto = re.sub(r"^\s*>\s?", "", texto, flags=re.MULTILINE)
        texto = re.sub(r"\n{3,}", "\n\n", texto)
        texto = re.sub(r"[ \t]{2,}", " ", texto)
        return texto.strip()

    def _carregar_dependencias_audio(self) -> None:
        if self._np is None:
            import numpy as np
            self._np = np
        if self._sd is None:
            import sounddevice as sd
            self._sd = sd

    def _carregar_dependencias_whisper(self) -> None:
        self._carregar_dependencias_audio()
        if self._WhisperModel is None:
            # Registra as DLLs dos wheels NVIDIA antes de importar CTranslate2.
            try:
                from hardware import preparar_runtime_cuda
                preparar_runtime_cuda()
            except Exception:
                LOGGER.debug("Não foi possível preparar DLLs CUDA; CPU continua disponível.", exc_info=True)
            from faster_whisper import WhisperModel
            self._WhisperModel = WhisperModel

    def _carregar_pygame(self):
        if self._pygame is None:
            import pygame
            self._pygame = pygame
        if not self._pygame.mixer.get_init():
            self._pygame.mixer.init()
        return self._pygame

    async def _gerar_audio(
        self, texto: str, genero: str, caminho: str,
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        import edge_tts

        voz = self.voz_feminina if genero == "feminina" else self.voz_masculina
        comunicador = edge_tts.Communicate(texto, voz, rate="+0%", volume="+0%", pitch="+0Hz")
        # O streaming permite cancelar a síntese sem esperar o arquivo inteiro.
        with open(caminho, "wb") as arquivo:
            async for trecho in comunicador.stream():
                if (cancel_event or self._tts_cancel).is_set():
                    break
                if trecho.get("type") == "audio":
                    arquivo.write(trecho["data"])

    def falar(
        self,
        texto: str,
        genero: str = "feminina",
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        texto = self.limpar_texto_voz(texto)
        if not texto:
            return

        # Cada reprodução possui seu próprio evento. Um clique em Parar não
        # pode ser perdido por uma limpeza de evento feita posteriormente pelo
        # worker de síntese.
        cancel_event = cancel_event or threading.Event()
        self._active_tts_cancel = cancel_event
        caminho = None
        with self._tts_lock:
            try:
                if cancel_event.is_set():
                    return
                fd, caminho = tempfile.mkstemp(prefix="gacia_tts_", suffix=".mp3")
                os.close(fd)
                self._temp_file = caminho
                asyncio.run(asyncio.wait_for(
                    self._gerar_audio(texto, genero, caminho, cancel_event), timeout=60
                ))

                if cancel_event.is_set():
                    return
                if not os.path.isfile(caminho) or os.path.getsize(caminho) == 0:
                    raise RuntimeError("O serviço de voz não gerou um arquivo de áudio válido.")

                pygame = self._carregar_pygame()
                if cancel_event.is_set():
                    return
                with self._lock:
                    pygame.mixer.music.load(caminho)
                    if cancel_event.is_set():
                        self._descarregar_audio()
                        return
                    pygame.mixer.music.play()
                    self.falando = True

                while pygame.mixer.music.get_busy():
                    if cancel_event.wait(0.04):
                        break

            except Exception as erro:
                if not cancel_event.is_set():
                    LOGGER.exception("Erro no Edge TTS/reprodução: %s", erro)
                    self.fallback_sapi(texto, cancel_event=cancel_event)
            finally:
                self.falando = False
                self._descarregar_audio()
                self._limpar_temp(caminho)
                if self._active_tts_cancel is cancel_event:
                    self._active_tts_cancel = self._tts_cancel

    def _descarregar_audio(self) -> None:
        pygame = self._pygame
        if pygame is None:
            return
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                unload = getattr(pygame.mixer.music, "unload", None)
                if callable(unload):
                    unload()
        except Exception:
            LOGGER.debug("Não foi possível descarregar o áudio.", exc_info=True)

    def parar(self, cancel_event: Optional[threading.Event] = None) -> None:
        """Solicita cancelamento sem manipular o mixer em outra thread.

        pygame.mixer.music é um recurso global e algumas builds/drivers do
        Windows não toleram stop/unload concorrentes com get_busy/load/play.
        O worker de falar() observa o evento (poll de 40 ms) e executa toda a
        limpeza no próprio thread que controla a reprodução.
        """
        with self._lock:
            evento = cancel_event or self._active_tts_cancel or self._tts_cancel
            evento.set()
            if cancel_event is None:
                self._tts_cancel.set()
        # Não chamar pygame.mixer.music.stop/unload daqui. A saída é encerrada
        # pelo finally de falar(), no mesmo thread que iniciou a reprodução.
        # O fallback SAPI também recebe o cancelamento; chamar engine.stop de
        # outro thread COM pode encerrar o processo em alguns drivers SAPI5.

    def _limpar_temp(self, caminho: Optional[str] = None) -> None:
        caminho = caminho or self._temp_file
        if caminho:
            try:
                if os.path.exists(caminho):
                    os.remove(caminho)
            except OSError:
                LOGGER.warning("Não foi possível remover o áudio temporário: %s", caminho)
        if caminho == self._temp_file:
            self._temp_file = None

    def fallback_sapi(
        self, texto: str, cancel_event: Optional[threading.Event] = None
    ) -> None:
        cancel_event = cancel_event or self._tts_cancel
        if cancel_event.is_set():
            return
        try:
            import pyttsx3
            engine = pyttsx3.init()
            self._sapi_engine = engine
            self._sapi_cancel_event = cancel_event
            if cancel_event.is_set():
                engine.stop()
                return
            engine.say(texto)
            # Loop externo: mantém o motor no mesmo thread que criou a engine,
            # permitindo observar cancelamento sem chamar COM/SAPI de outra thread.
            start_loop = getattr(engine, "startLoop", None)
            iterate = getattr(engine, "iterate", None)
            end_loop = getattr(engine, "endLoop", None)
            is_busy = getattr(engine, "isBusy", None)
            if callable(start_loop) and callable(iterate) and callable(is_busy):
                start_loop(False)
                try:
                    while is_busy() and not cancel_event.wait(0.03):
                        iterate()
                finally:
                    try:
                        engine.stop()
                    finally:
                        if callable(end_loop):
                            end_loop()
            else:
                # Compatibilidade com engines simplificadas de terceiros. Neste
                # fallback o cancelamento é observado ao retornar de runAndWait.
                engine.runAndWait()
                engine.stop()
        except Exception:
            if not cancel_event.is_set():
                LOGGER.exception("Falha no fallback SAPI.")
        finally:
            if self._sapi_cancel_event is cancel_event:
                self._sapi_engine = None
                self._sapi_cancel_event = None

    def _criar_modelo_cpu(self):
        self._carregar_dependencias_whisper()
        modelo = self._WhisperModel(
            self.modelo_whisper_nome,
            device="cpu",
            compute_type="int8",
            cpu_threads=max(2, min(4, os.cpu_count() or 4)),
        )
        self.modelo_whisper = modelo
        self.whisper_device = "cpu"
        self.whisper_compute_type = "int8"
        LOGGER.info("Whisper carregado na CPU (INT8).")
        return modelo

    @serialize_gpu_task
    def _carregar_whisper(self):
        if self.modelo_whisper is not None:
            return self.modelo_whisper

        self._carregar_dependencias_whisper()
        LOGGER.info(
            "Carregando Whisper (%s) no dispositivo preferido: %s",
            self.modelo_whisper_nome,
            self.device_preferido,
        )

        if self.device_preferido == "cpu":
            return self._criar_modelo_cpu()

        # Mesmo em CUDA explicitamente selecionado, não iniciar uma segunda
        # carga se a placa já estiver em condição térmica/VRAM crítica.
        if self.device_preferido == "cuda":
            try:
                from resource_manager import get_gpu_status
                status = get_gpu_status(refresh=True)
                if status is not None and (
                    (status.temperature_c is not None and status.temperature_c >= 85)
                    or (status.utilization_percent is not None and status.utilization_percent >= 95)
                    or (status.memory_free_mb is not None and status.memory_free_mb < 1500)
                ):
                    motivo = (
                        f"temperatura {status.temperature_c} °C" if status.temperature_c is not None and status.temperature_c >= 85
                        else f"utilização {status.utilization_percent}%" if status.utilization_percent is not None and status.utilization_percent >= 95
                        else f"VRAM livre {status.memory_free_mb} MB"
                    )
                    LOGGER.warning("CUDA solicitado para Whisper, mas GPU está sob carga (%s); usando CPU INT8.", motivo)
                    return self._criar_modelo_cpu()
            except Exception:
                LOGGER.warning("Não foi possível validar o estado da GPU; respeitando configuração CUDA explícita.")

        if self.device_preferido == "auto":
            try:
                import ctranslate2
                quantidade_cuda = int(ctranslate2.get_cuda_device_count())
            except Exception as erro_cuda:
                quantidade_cuda = 0
                LOGGER.info("CUDA não está disponível para Faster-Whisper: %s", erro_cuda)
            if quantidade_cuda <= 0:
                LOGGER.info("Modo automático: usando CPU; não há runtime CUDA utilizável para Faster-Whisper.")
                return self._criar_modelo_cpu()
            try:
                from resource_manager import get_gpu_status, whisper_backend_decision
                status = get_gpu_status(refresh=True)
                backend, motivo = whisper_backend_decision(status)
                if backend != "cuda":
                    LOGGER.warning("Whisper automático em CPU: %s", motivo)
                    return self._criar_modelo_cpu()
                LOGGER.info("Whisper automático pode usar CUDA: %s", motivo)
            except Exception:
                # Sem leitura térmica confiável, o modo automático prefere CPU.
                LOGGER.warning("Não foi possível validar a condição térmica; Whisper automático ficará na CPU.")
                return self._criar_modelo_cpu()

        try:
            modelo = self._WhisperModel(self.modelo_whisper_nome, device="cuda", compute_type="float16")
            self.modelo_whisper = modelo
            self.whisper_device = "cuda"
            self.whisper_compute_type = "float16"
            LOGGER.info("Whisper carregado na GPU CUDA (FP16).")
            return modelo
        except Exception as erro_gpu:
            LOGGER.warning("Whisper não iniciou na GPU (%s). Tentando CPU INT8.", erro_gpu)
            return self._criar_modelo_cpu()

    def iniciar_escuta(
        self,
        callback: Callable[[str], None],
        callback_erro: Optional[Callable[[str], None]] = None,
        *,
        modo_continuo: bool = False,
        callback_pronto: Optional[Callable[[], None]] = None,
        callback_finalizado: Optional[Callable[[], None]] = None,
    ) -> bool:
        if not callable(callback):
            raise ValueError("O callback de transcrição é obrigatório.")
        if self._escuta_thread and self._escuta_thread.is_alive():
            # Não inicia uma segunda captura enquanto a anterior ainda finaliza.
            return False

        self._escuta_stop.clear()
        self._audio_queue = queue.Queue(maxsize=24)
        self._escuta_thread = threading.Thread(
            target=self._loop_escuta,
            args=(callback, callback_erro, bool(modo_continuo), callback_pronto, callback_finalizado),
            daemon=True,
            name="GacIA-Whisper",
        )
        try:
            self._escuta_thread.start()
            return True
        except Exception:
            LOGGER.exception("Não foi possível iniciar a thread de captura.")
            self._escuta_thread = None
            return False

    def parar_escuta(self) -> None:
        """Solicita parada sem fechar PortAudio de outra thread.

        O próprio worker encerra o stream no finally. Fechar InputStream na
        thread da interface enquanto o callback está ativo pode travar ou
        derrubar o processo em alguns drivers do Windows.
        """
        self._escuta_stop.set()
        self.ouvindo = False
        self.microfone_silenciado = False

    def definir_microfone_silenciado(self, silenciado: bool) -> None:
        """Silencia a entrada sem parar o stream de áudio nem o TTS."""
        self.microfone_silenciado = bool(silenciado)
        if self.microfone_silenciado:
            # Descarta áudio já enfileirado para que ele não seja transcrito
            # depois que o usuário silenciar o microfone.
            while True:
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    break

    @staticmethod
    def _calcular_limiares_vad(ruido_ambiente: float):
        # Histerese: é mais difícil iniciar fala do que continuar um trecho.
        ruido = max(0.0, float(ruido_ambiente or 0.0))
        limite_inicio = max(0.0012, ruido * 2.0)
        limite_fim = max(0.0007, ruido * 1.45)
        return limite_inicio, min(limite_fim, limite_inicio * 0.85)

    def _loop_escuta(
        self, callback, callback_erro, modo_continuo=True,
        callback_pronto=None, callback_finalizado=None,
    ) -> None:
        stream = None
        try:
            self._carregar_dependencias_audio()
            modelo = self._carregar_whisper()
            if self._escuta_stop.is_set():
                return

            samplerate = 16000
            bloco = 1600  # 100 ms: boa responsividade sem excesso de callbacks.

            def emitir_transcricao(texto: str) -> None:
                # Se o usuário silenciar durante a inferência, descarte também
                # o resultado que estava sendo processado naquele instante.
                if modo_continuo and self.microfone_silenciado:
                    return
                callback(texto)

            def audio_callback(indata, frames, time_info, status):
                if self._escuta_stop.is_set() or self.microfone_silenciado:
                    return
                if status:
                    LOGGER.debug("Aviso de captura de áudio: %s", status)
                audio = indata[:, 0].copy()
                try:
                    self._audio_queue.put_nowait(audio)
                except queue.Full:
                    # Prioriza áudio recente em vez de transcrever uma fila atrasada.
                    try:
                        self._audio_queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self._audio_queue.put_nowait(audio)
                    except queue.Full:
                        pass

            try:
                stream = self._sd.InputStream(
                    samplerate=samplerate,
                    channels=1,
                    dtype="float32",
                    blocksize=bloco,
                    callback=audio_callback,
                )
            except Exception as erro_16k:
                # Alguns drivers do Windows não aceitam 16 kHz diretamente.
                # Usa a taxa nativa do dispositivo e reamostra somente os trechos
                # reconhecidos para o formato esperado pelo Whisper.
                try:
                    dispositivo = self._sd.query_devices(kind="input")
                    samplerate = int(dispositivo.get("default_samplerate") or 48000)
                    if samplerate < 8000 or samplerate > 192000:
                        raise ValueError("Taxa de amostragem do microfone inválida.")
                    bloco = max(1, int(samplerate * 0.1))
                    stream = self._sd.InputStream(
                        samplerate=samplerate,
                        channels=1,
                        dtype="float32",
                        blocksize=bloco,
                        callback=audio_callback,
                    )
                    LOGGER.warning(
                        "Microfone não aceitou 16 kHz (%s); usando taxa nativa %s Hz.",
                        erro_16k, samplerate,
                    )
                except Exception:
                    raise RuntimeError(
                        "Não foi possível abrir o microfone. Verifique o dispositivo de entrada "
                        "padrão e as permissões do Windows."
                    ) from erro_16k

            self._audio_stream = stream
            stream.start()
            self.ouvindo = True
            LOGGER.info("Microfone ativo em %s Hz; calibrando ruído ambiente.", samplerate)

            # Na captura ao vivo, o reconhecimento depende de detectar o silêncio
            # entre frases. Uma calibração curta evita que ventiladores e ruído
            # constante sejam confundidos com fala contínua.
            niveis_calibracao = []
            for _ in range(8):
                if self._escuta_stop.is_set():
                    break
                try:
                    amostra = self._audio_queue.get(timeout=0.25)
                except queue.Empty:
                    continue
                nivel = float(self._np.sqrt(self._np.mean(amostra ** 2)))
                niveis_calibracao.append(nivel)
            if niveis_calibracao:
                ruido_ambiente = float(self._np.percentile(niveis_calibracao, 70))
            else:
                ruido_ambiente = 0.0005
            LOGGER.info("Ruído ambiente calibrado: RMS %.5f em %s Hz.", ruido_ambiente, samplerate)

            segmentos = []
            pre_buffer = deque(maxlen=4)
            falando = False
            silencio = 0
            limite_silencio = 7
            limite_minimo_audio = int(samplerate * 0.30)
            ultimo_rms_log = 0

            if self._escuta_stop.is_set():
                return
            if callable(callback_pronto):
                try:
                    callback_pronto()
                except Exception:
                    LOGGER.exception("Erro no callback de microfone pronto.")

            while not self._escuta_stop.is_set():
                try:
                    audio = self._audio_queue.get(timeout=0.2)
                except queue.Empty:
                    if self.microfone_silenciado:
                        segmentos = []
                        pre_buffer.clear()
                        falando = False
                        silencio = 0
                    continue

                if self.microfone_silenciado:
                    segmentos = []
                    pre_buffer.clear()
                    falando = False
                    silencio = 0
                    continue
                volume = float(self._np.sqrt(self._np.mean(audio ** 2)))
                # Registra nível de sinal periodicamente para diagnosticar
                # microfone ativo com sinal baixo/silencioso.
                agora = __import__("time").monotonic()
                if agora - ultimo_rms_log >= 5:
                    LOGGER.info("Nível do microfone (RMS): %.5f; limiar: %.5f", volume, max(0.0012, ruido_ambiente * 1.6))
                    ultimo_rms_log = agora
                limite_inicio, limite_fim = self._calcular_limiares_vad(ruido_ambiente)
                if not falando and volume >= limite_inicio:
                    segmentos = list(pre_buffer)
                    falando = True
                    segmentos.append(audio)
                    silencio = 0
                elif not falando:
                    # Atualiza o piso de ruído lentamente enquanto não há fala.
                    ruido_ambiente = max(0.0001, ruido_ambiente * 0.96 + volume * 0.04)
                    pre_buffer.append(audio)
                else:
                    segmentos.append(audio)
                    if volume >= limite_fim:
                        silencio = 0
                    else:
                        silencio += 1
                    if silencio >= limite_silencio:
                        falando = False
                        audio_completo = self._np.concatenate(segmentos)
                        segmentos = []
                        silencio = 0
                        if len(audio_completo) < limite_minimo_audio or self._escuta_stop.is_set():
                            continue
                        LOGGER.info("Áudio capturado; iniciando transcrição.")
                        audio_whisper = self._reamostrar_audio(audio_completo, samplerate, 16000)
                        transcreveu = self._transcrever(modelo, audio_whisper, emitir_transcricao)
                        modelo = self.modelo_whisper or modelo
                        if transcreveu and not modo_continuo:
                            self._escuta_stop.set()
                            break

            # Se o usuário apertar Parar no meio da fala, não descarte o áudio.
            if falando and segmentos and not self.microfone_silenciado:
                audio_final = self._np.concatenate(segmentos)
                if len(audio_final) >= limite_minimo_audio:
                    LOGGER.info("Finalizando trecho de fala ao parar a captura.")
                    audio_whisper = self._reamostrar_audio(audio_final, samplerate, 16000)
                    self._transcrever(modelo, audio_whisper, emitir_transcricao, forcar=True)

        except Exception as erro:
            LOGGER.exception("Erro no sistema de reconhecimento de voz.")
            if callable(callback_erro) and not self._escuta_stop.is_set():
                try:
                    callback_erro(str(erro))
                except Exception:
                    LOGGER.exception("Erro no callback de falha de voz.")
        finally:
            self.ouvindo = False
            if stream is not None:
                try:
                    stream.stop()
                except Exception:
                    pass
                try:
                    stream.close()
                except Exception:
                    pass
            if self._audio_stream is stream:
                self._audio_stream = None
            LOGGER.info("Captura de áudio encerrada.")
            if callable(callback_finalizado):
                try:
                    callback_finalizado()
                except Exception:
                    LOGGER.exception("Erro no callback de encerramento do microfone.")

    def _reamostrar_audio(self, audio, taxa_origem: int, taxa_destino: int):
        """Converte áudio mono para a taxa exigida pelo Whisper sem dependências extras."""
        if taxa_origem == taxa_destino:
            return audio
        quantidade = int(round(len(audio) * taxa_destino / float(taxa_origem)))
        if quantidade <= 0:
            return self._np.asarray([], dtype="float32")
        posicoes = self._np.linspace(0, max(0, len(audio) - 1), quantidade)
        return self._np.interp(posicoes, self._np.arange(len(audio)), audio).astype("float32")

    def _executar_transcricao(self, modelo, audio) -> str:
        segmentos, _info = modelo.transcribe(
            audio,
            language=self.language,
            beam_size=3,
            vad_filter=False,
            condition_on_previous_text=False,
            temperature=0.0,
        )
        return " ".join(
            segmento.text.strip()
            for segmento in segmentos
            if getattr(segmento, "text", "").strip()
        ).strip()

    @serialize_gpu_task
    def _transcrever(self, modelo, audio, callback, forcar: bool = False) -> bool:
        if self._escuta_stop.is_set() and not forcar:
            return False
        # Reavalia apenas antes de cada lote de transcrição (nunca por token do
        # Ollama). Se a GPU esquentar durante o chat ao vivo, migra o Whisper.
        if self.whisper_device == "cuda":
            try:
                from resource_manager import get_gpu_status
                status = get_gpu_status(refresh=True)
                if status and status.temperature_c is not None and status.temperature_c >= 85:
                    LOGGER.warning("GPU a %s °C; alternando Whisper para CPU INT8 para evitar carga concorrente.", status.temperature_c)
                    modelo = None
                    self.modelo_whisper = None
                    gc.collect()
                    modelo = self._criar_modelo_cpu()
            except Exception:
                LOGGER.debug("Não foi possível reavaliar temperatura antes da transcrição.", exc_info=True)
        try:
            texto = self._executar_transcricao(modelo, audio)
        except Exception as erro_gpu:
            if self.whisper_device != "cuda" or (self._escuta_stop.is_set() and not forcar):
                LOGGER.exception("Erro durante a transcrição do Whisper.")
                return False
            LOGGER.warning("Falha durante inferência CUDA (%s). Alternando para CPU INT8.", erro_gpu)
            try:
                # Solta a última referência ao modelo CUDA antes de criar o CPU.
                modelo = None
                self.modelo_whisper = None
                gc.collect()
                modelo_cpu = self._criar_modelo_cpu()
                modelo = modelo_cpu
                texto = self._executar_transcricao(modelo_cpu, audio)
            except Exception:
                LOGGER.exception("A transcrição também falhou na CPU.")
                return False

        if texto and (not self._escuta_stop.is_set() or forcar):
            LOGGER.info("Transcrição concluída (%d caracteres).", len(texto))
            try:
                callback(texto)
                return True
            except Exception:
                LOGGER.exception("Erro ao enviar a transcrição para a interface.")
        return False

    def fechar(self) -> None:
        # O worker de TTS é responsável por parar/descarregar o mixer. Não
        # manipule o mixer na thread da interface durante o encerramento.
        self.parar()
        self.parar_escuta()
        self.modelo_whisper = None
        gc.collect()
