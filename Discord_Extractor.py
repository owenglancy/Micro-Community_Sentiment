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
            is_bot: bool = True,
            before_id: Optional[str] = None
    ):
        self.channel_id = channel_id
        self.base_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        self.headers = {
            "Authorization": f"Bot {auth_token}" if is_bot else auth_token,
            "User-Agent": "DiscordBot (https://github.com, 1.0)"
        }
        self.output_file = f"{out_dir}/{output_file}.jsonl"
        self.total_fetched = 0
        self.last_message_id: Optional[str] = before_id
        self.shutdown_requested = False
        self.rate_limit_delay = 1.0
        self.max_server_retries = 5
        self.server_error_count = 0     # consecutive 5xx responses
        self.export_failed = False      # True if the channel stopped before reaching its end
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
            self._shutdown_sequence()

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

    def append_batch(self, batch) -> None:
        with open(self.output_file,'a', encoding = "utf-8") as f:
            for msg in batch:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self.total_fetched += len(batch)

    async def _fetch_message_loop(self) -> None:
        async with aiohttp.ClientSession(headers=self.headers) as session:
            while not self.shutdown_requested:
                try:
                    messages = await self._fetch_message_batch(session)
                    if messages is None:
                        continue
                    if not messages:
                        break
                    self.server_error_count = 0
                    self.append_batch(messages)
                    self.last_message_id = messages[-1]["id"]

                    self.logger.info(f"Fetched {len(messages)} messages | Total: {(self.total_fetched)}")

                    # Dynamic delay adjustment
                    self.rate_limit_delay = max(self.rate_limit_delay * 0.9, 0.5)
                    await asyncio.sleep(self.rate_limit_delay)

                except aiohttp.ClientError as e:
                    self.logger.error(f"Network error: {str(e)}")
                    await asyncio.sleep(self.rate_limit_delay * 2)
                except json.JSONDecodeError:
                    self.logger.critical("Invalid JSON response")
                    self.export_failed = True
                    break

    async def _fetch_message_batch(self, session: aiohttp.ClientSession) -> Optional[List[Dict]]:
        params = {"limit": "100"}
        if self.last_message_id:
            params["before"] = self.last_message_id

        async with session.get(self.base_url, params=params) as response:
            if response.status == 200:
                return await response.json()
            return await self._handle_api_error(response)


    async def _handle_api_error(self, response: aiohttp.ClientResponse) -> Optional[List[Dict]]:
        """Returns None to retry the same request, or [] to stop this channel."""
        if response.status == 429:
            retry_after = float(response.headers.get("Retry-After", 5))
            self.logger.error(f"Rate limited - retrying after {retry_after}s")
            await asyncio.sleep(retry_after)
            return None

        if response.status >= 500:
            self.server_error_count += 1
            if self.server_error_count <= self.max_server_retries:
                delay = 2 ** self.server_error_count
                self.logger.error(
                    f"Server error {response.status} - retry "
                    f"{self.server_error_count}/{self.max_server_retries} in {delay}s"
                )
                await asyncio.sleep(delay)
                return None

        # Out of retries, or a status that retrying won't fix (401, 403, 404...)
        self.logger.critical(f"API Error {response.status}: {await response.text()}")
        self.export_failed = True
        return []

    def _load_existing_messages(self) -> None:
        if not os.path.exists(self.output_file):
            return

        last_id = None      # id from the last valid line (the oldest message saved)
        offset = 0          # bytes consumed so far
        good_end = 0        # byte position just after the last valid line
        bad_tail = False    # True if the most recent non-blank line was unreadable
        last_raw = b""

        try:
            # Binary mode so offsets are exact byte positions we can truncate to
            with open(self.output_file, "rb") as f:
                for line_no, raw in enumerate(f, start=1):
                    offset += len(raw)
                    if not raw.strip():
                        continue
                    last_raw = raw
                    try:
                        # ValueError covers both JSONDecodeError and UnicodeDecodeError
                        msg_id = json.loads(raw.decode("utf-8"))["id"]
                    except (ValueError, KeyError, TypeError):
                        self.logger.warning(f"Skipping unreadable line {line_no}")
                        bad_tail = True
                        continue
                    last_id = msg_id
                    good_end = offset
                    bad_tail = False

            if bad_tail:
                # Unreadable data at the end (e.g. crash mid-write): cut it off so
                # the next append starts on a clean line instead of merging into it
                with open(self.output_file, "r+b") as f:
                    f.truncate(good_end)
                self.logger.warning(f"Truncated damaged tail; file now ends at byte {good_end}")
            elif last_raw and not last_raw.endswith(b"\n"):
                # Last line is valid but missing its newline; add it before appending
                with open(self.output_file, "ab") as f:
                    f.write(b"\n")

            if last_id is not None:
                self.last_message_id = last_id
        except IOError as e:
            self.logger.critical(f"Error loading existing data: {str(e)}")


    def _shutdown_sequence(self) -> None:
        self.logger.info("\nInitiating graceful shutdown...")

        if self.export_failed:
            self.logger.critical(
                f"Export of channel {self.channel_id} is INCOMPLETE - "
                f"saved{self.total_fetched} messages this run, rerun to resume")
        else:
            self.logger.info(f"Successfully saved {(self.total_fetched)} messages")


load_dotenv()
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Discord channel to JSONL")
    parser.add_argument("channel_ids", nargs="+", help="Discord channel ID(s) to export")
    parser.add_argument("--out_dir", default="exports")
    parser.add_argument("--before")
    args = parser.parse_args()
    AUTH_TOKEN = os.environ.get("DISCORD_TOKEN")
    if not AUTH_TOKEN:
        sys.exit("Error: DISCORD_TOKEN not found in environment variables.")

    failed_channels = []

    for channel_id in args.channel_ids:
        exporter = DiscordMessageExporter(
            channel_id= channel_id,
            auth_token=AUTH_TOKEN,
            out_dir= args.out_dir,
            output_file=channel_id,
            before_id = args.before
    )

        try:
            asyncio.run(exporter.run())
            if exporter.export_failed:
                failed_channels.append(channel_id)
            if exporter.shutdown_requested:
                break
        except KeyboardInterrupt:
            print("\nShutdown completed safely")
            break

    if failed_channels:
        sys.exit(f"Incomplete exports: {', '.join(failed_channels)}")
