"""
    Implementation of KafkaProducerThread and KafkaProducerSwarm classes.
        - KafkaProducerThread: A thread that produces messages to a Kafka topic.
        - KafkaProducerSwarm: A collection of KafkaProducerThread instances.
    
    Usage:
        - Create a KafkaProducerSwarm instance with the desired settings.
        - KafkaProducerSwarm will create a KafkaProducerThread for each fetch function.
        - Stop the swarm to halt message production and close the producer instances.
"""

import json
import threading
import asyncio
import time
import fire
from kafka import KafkaProducer
from typing import Callable, List, NoReturn
from settings import settings
from logger import get_logger
from models import CommonDocument
from tools import NewsFetcher, TelegramChannelsFetcher

logger = get_logger(__name__)


class KafkaProducerThread(threading.Thread):
    """
    A thread that produces messages to a Kafka topic.

    Attributes:
        producer_id (int): Identifier for the producer instance.
        topic (str): The Kafka topic to which messages will be produced.
        fetch_function (Callable): Function to fetch data to be sent to Kafka.
        producer (KafkaProducer): Kafka producer instance.
        wait_window_sec (int): Time to wait between message production in seconds.
        running (bool): Control flag for the running state of the thread.
    """

    def __init__(
        self,
        producer_id: int,
        producer: KafkaProducer,
        topic: str,
        fetch_function: Callable,
        is_async = False
    ) -> None:
        super().__init__(daemon=True)
        self.producer_id = f"KafkaProducerThread #{producer_id}"
        self.producer = producer  # Use the shared producer
        self.topic = topic
        self.fetch_function = fetch_function
        self.wait_window_sec = settings.FETCH_WAIT_WINDOW  # Adjust as needed
        self.running = threading.Event()
        self.is_async = is_async
        self.running.set()

    def run(self) -> NoReturn:
        """Continuously fetch and send messages to a Kafka topic."""
        while self.running.is_set():
            try:
                if self.is_async:
                    print("Starting event loop for async fetcher", type(self.fetch_function))
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    # future = asyncio.run_coroutine_threadsafe(corutine_object, loop)
                    try:
                        messages: List[CommonDocument] = loop.run_until_complete(self.fetch_function(loop))
                        print(messages)
                    except Exception as e:
                        print("something went wrong with tele", e)
                        messages = []

                else:
                    logger.info("Calling fetch function")
                    messages: List[CommonDocument] = self.fetch_function()

                
                if messages:
                    messages = [msg.to_kafka_payload() for msg in messages]
                    self.producer.send(self.topic, value=messages)
                    self.producer.flush()
                logger.info(
                    f"Producer : {self.producer_id} sent: {len(messages)} msgs."
                )
                time.sleep(self.wait_window_sec)
            except Exception as e:
                logger.error(f"Error in producer worker {self.producer_id}: {e}")
                self.running.clear()  # Stop the thread on error

    def stop(self) -> None:
        """Signals the thread to stop running and closes the Kafka producer."""
        self.running.clear()
        self.producer.close()
        self.join()


class KafkaProducerSwarm:
    """
    Manages a swarm of KafkaProducerThread instances for concurrent data fetching and Kafka message production.

    Attributes:
        producer_threads (List[KafkaProducerThread]): A list of KafkaProducerThread instances.
    """

    def __init__(
        self,
        producer: KafkaProducer,
        topic: str,
        fetch_functions: List[Callable],
        async_fetch_functions: List[Callable]
    ):
        self.sync_producer_threads = [
            KafkaProducerThread(i, producer, topic, fetch_function, is_async=False)
            for i, fetch_function in enumerate(fetch_functions)
        ]

        self.async_producer_threads = [
            KafkaProducerThread(i + len(self.sync_producer_threads), producer, topic, async_fetch_function, is_async=True)
            for i, async_fetch_function in enumerate(async_fetch_functions)
        ]

        self.producer_threads = self.sync_producer_threads + self.async_producer_threads

        
    def start(self) -> None:
        """Starts all producer threads."""
        for thread in self.producer_threads:
            thread.start()

    def stop(self) -> None:
        """Stops all producer threads and waits for them to terminate."""
        for thread in self.producer_threads:
            thread.stop()
        for thread in self.producer_threads:
            thread.join()


def create_producer() -> KafkaProducer:
    """Initializes and returns a KafkaProducer instance."""
    return KafkaProducer(
        bootstrap_servers=settings.UPSTASH_KAFKA_ENDPOINT,
        sasl_mechanism=settings.UPSTASH_KAFKA_SASL_MECHANISM,
        security_protocol=settings.UPSTASH_KAFKA_SECURITY_PROTOCOL,
        sasl_plain_username=settings.UPSTASH_KAFKA_UNAME,
        sasl_plain_password=settings.UPSTASH_KAFKA_PASS,
        api_version_auto_timeout_ms=100000,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

async def waitme():
    await asyncio.sleep(1)
    print("slept a bit")
    return "heeeeeey"

def main():
    producer = create_producer()
    fetcher = NewsFetcher()
    tele_fetcher = TelegramChannelsFetcher()

    multi_producer = KafkaProducerSwarm(
        producer=producer,
        topic=settings.UPSTASH_KAFKA_TOPIC,
        fetch_functions=fetcher.sources,
        async_fetch_functions=[tele_fetcher.fetch_news_from_telegram]
    )

    try:
        multi_producer.start()
        while True:
            time.sleep(1)
    finally:
        multi_producer.stop()
        producer.close()


if __name__ == "__main__":
    fire.Fire(main)
