# graph/voice_utils.py
import asyncio
from faster_whisper import WhisperModel
import edge_tts

# --- PARCHE DE COMPATIBILIDAD PYAV ---
import av
_original_av_open = av.open
def _patched_av_open(*args, **kwargs):
    kwargs.pop("metadata_errors", None)
    return _original_av_open(*args, **kwargs)
av.open = _patched_av_open
# -------------------------------------

# Inicializamos el modelo de Whisper una sola vez
stt_model = WhisperModel("base", device="cpu", compute_type="int8")
VOICE = "es-ES-AlvaroNeural"  # O "es-MX-DaliaNeural" para acento latino

def audio_to_text(audio_path: str) -> str:
    """Convierte la nota de voz del usuario en texto usando faster-whisper."""
    segments, _ = stt_model.transcribe(audio_path, language="es")
    text = " ".join([segment.text for segment in segments])
    return text.strip()

# Alias por compatibilidad
transcribe_audio_file = audio_to_text


async def _generate_audio(text: str, output_path: str) -> None:
    """Función interna asíncrona para edge-tts."""
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(output_path)


def text_to_audio(text: str, output_path: str) -> None:
    """Versión síncrona para que Streamlit pueda llamarla directamente sin errores."""
    asyncio.run(_generate_audio(text, output_path))

# Alias por compatibilidad
generate_tts_file = text_to_audio