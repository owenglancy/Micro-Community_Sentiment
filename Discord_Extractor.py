# Based on discord-message-exporter by ByteScrape (https://github.com/ByteScrape/discord-message-exporter)


import asyncio
import argparse 
import json
import logging
import os
import signal
import sys
from typing import List, Dict, Optional
import aiohttp
from dotenv import load_dotenv
from utils.logger import configure_logging


class DiscordMessageExporter:
    def __init__(
            self,
            channel_id: str,
            auth_token: str,
            output_file:str = "messages",
            out_dir: str = "exports",
            save_interval: int = 50,
            is_bot: bool = True
    ):
        self.channel_id = channel_id
        self.base_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        self.headers = {
            "Authorization": f"Bot {auth_token}" if is_bot else auth_token,
            "User-Agent": "DiscordBot (https://github.com, 1.0)"
        }
        self.output_file = f"{out_dir}/{output_file}.json"
        self.save_interval = save_interval
        self.messages: List[Dict] = []
        self.last_message_id: Optional[str] = None
        self.shutdown_requested = False
        self.rate_limit_delay = 1.0
        configure_logging(
            name="discord-message-exporter",
            path="logs",
            level=logging.DEBUG,
            save=False
        )
        self.logger = logging.getLogger("discord-message-exporter")
        self.signal_registered = False

    def _trigger_graceful_shutdown(self) -> None:
        self.shutdown_requested = True

    async def run(self) -> None:
        """Main execution flow with safety wrappers"""
        if not self.signal_registered:
            self._register_signal_handlers()

        try:
            self._load_existing_messages()
            await self._fetch_message_loop()
        finally:
            await self._shutdown_sequence()

    def _register_signal_handlers(self) -> None:
        """Set up cross-platform interrupt handling"""
        if sys.platform == "win32":
            import win32api
            win32api.SetConsoleCtrlHandler(
                lambda _: self._trigger_graceful_shutdown(), True
            )
        else:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGINT, self._trigger_graceful_shutdown)
        self.signal_registered = True

    async def _fetch_message_loop(self) -> None:
        async with aiohttp.ClientSession(headers=self.headers) as session:
            while not self.shutdown_requested:
                try:
                    messages = await self._fetch_message_batch(session)
                    if not messages:
                        break

                    self.messages.extend(messages)
                    self.last_message_id = messages[-1]["id"]

                    if len(self.messages) % self.save_interval == 0:
                        self._atomic_save()

                    self.logger.info(f"Fetched {len(messages)} messages | Total: {len(self.messages)}")

                    # Dynamic delay adjustment
                    self.rate_limit_delay = max(self.rate_limit_delay * 0.9, 0.5)
                    await asyncio.sleep(self.rate_limit_delay)

                except aiohttp.ClientError as e:
                    self.logger.error(f"Network error: {str(e)}")
                    await asyncio.sleep(self.rate_limit_delay * 2)
                except json.JSONDecodeError:
                    self.logger.critical("Invalid JSON response")
                    break

    async def _fetch_message_batch(self, session: aiohttp.ClientSession) -> List[Dict]:
        params = {"limit": "100"}
        if self.last_message_id:
            params["before"] = self.last_message_id

        try:
            async with session.get(self.base_url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                return await self._handle_api_error(response)
        except asyncio.CancelledError:
            self._atomic_save()
            raise

    async def _handle_api_error(self, response: aiohttp.ClientResponse) -> List[Dict]:
        if response.status == 429:
            retry_after = float(response.headers.get("Retry-After", 5))
            self.logger.error(f"Rate limited - retrying after {retry_after}s")
            await asyncio.sleep(retry_after)
            return []

        self.logger.critical(f"API Error {response.status}: {await response.text()}")
        return []

    def _load_existing_messages(self) -> None:
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, "r") as f:
                    existing = json.load(f)
                    if isinstance(existing, list):
                        self.messages = existing
                        self.last_message_id = existing[-1]["id"] if existing else None
            except (json.JSONDecodeError, IOError) as e:
                self.logger.critical(f"Error loading existing data: {str(e)}")

    def _atomic_save(self) -> None:
        temp_path = f"{self.output_file}.tmp"
        try:
            with open(temp_path, "w") as f:
                json.dump(self.messages, f, indent=2)
            os.replace(temp_path, self.output_file)
        except IOError as e:
            self.logger.critical(f"Save failed: {str(e)}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

    async def _shutdown_sequence(self) -> None:
        self.logger.info("\nInitiating graceful shutdown...")

        for attempt in range(3):
            try:
                self._atomic_save()
                self.logger.info(f"Successfully saved {len(self.messages)} messages")
                break
            except IOError as e:
                self.logger.error(f"Save failed (attempt {attempt + 1}): {str(e)}")
                await asyncio.sleep(0.5 * (attempt + 1))

load_dotenv()
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Discord channel to JSONL")
    parser.add_argument("channel_ids", nargs="+", help="Discord channel ID(s) to export")
    parser.add_argument("--out_dir", default="exports")
    args = parser.parse_args()
    AUTH_TOKEN = os.environ.get("DISCORD_TOKEN")
    if not AUTH_TOKEN:
        sys.exit("Error: DISCORD_TOKEN not found in environment variables.")

    for channel_id in args.channel_ids:
        exporter = DiscordMessageExporter(
            channel_id= channel_id,
            auth_token=AUTH_TOKEN,
            out_dir= args.out_dir,
            output_file=channel_id,
            save_interval=50
    )

        try:
            asyncio.run(exporter.run())
            if exporter.shutdown_requested:
                break
        except KeyboardInterrupt:
            print("\nShutdown completed safely")
            break
