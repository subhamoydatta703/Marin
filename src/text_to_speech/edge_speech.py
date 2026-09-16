import asyncio
import subprocess
import edge_tts


async def speak(text):
    # create Edge TTS
    communicate = edge_tts.Communicate(text,"en-IN-NeerjaNeural",rate="-3%")

    # start ffplay
    process = subprocess.Popen(
        [
            "ffplay",
            "-nodisp",
            "-autoexit",
            "-loglevel", "quiet",
            "-i", "pipe:0"
        ],
        stdin=subprocess.PIPE
    )

    # get audio chunks from Edge TTS
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            # send audio to ffplay
            process.stdin.write(chunk["data"])
            process.stdin.flush()

    # tell ffplay there is no more data
    process.stdin.close()

    # wait for ffplay to finish
    process.wait()


