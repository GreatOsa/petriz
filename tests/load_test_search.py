import asyncio
import httpx
import random
import time
from typing import Dict, Any
import logging
import rich
from faker import Faker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
SEARCH_URL = f"{BASE_URL}/search"
HEADERS = {
    "x-client-id": "slb_client_T6WmX7iwEt9xyq4B",
    "x-client-secret": "slb_apisecret_H4kE2SIK5Jng8jxTaQqdZ6OB",
    # "Authorization": "AuthToken petriz_authtoken_1XeLVSZqmIO3WFND6KY4vEkw",
}

fake = Faker()
# Generate a pool of random words for queries
SAMPLE_QUERIES = [fake.word() for _ in range(200)]  # Create a pool of 200 random words
SAMPLE_TOPICS = ["geology", "engineering", "chemistry", "physics", "operations"]
SAMPLE_SOURCES = ["SPE", "API", "NACE", "ISO", "SLB"]


class RateLimitedClient:
    def __init__(self, base_delay: float = 0.1, max_delay: float = 30):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.current_delay = base_delay
        self.last_request_time = 0

    async def make_request(
        self, client: httpx.AsyncClient, url: str, params: Dict[str, Any]
    ) -> Dict:
        while True:
            try:
                # Ensure minimum delay between requests
                time_since_last = time.time() - self.last_request_time
                if time_since_last < self.current_delay:
                    await asyncio.sleep(self.current_delay - time_since_last)

                self.last_request_time = time.time()
                response = await client.get(url, params=params, headers=HEADERS)

                if response.status_code == 429:  # Rate limited
                    self.current_delay = min(self.current_delay * 2, self.max_delay)
                    await asyncio.sleep(self.current_delay)
                    continue

                self.current_delay = max(self.base_delay, self.current_delay * 0.75)
                return response.json()

            except Exception as e:
                logger.error(f"Error making request: {e}")
                await asyncio.sleep(self.current_delay)
                self.current_delay = min(self.current_delay * 2, self.max_delay)


def generate_random_params() -> Dict[str, Any]:
    params = {}

    # 70% chance to include query
    if random.random() < 0.7:
        # Use faker to generate more realistic search queries
        if random.random() < 0.5:
            # Single word query
            params["query"] = fake.word()
        else:
            # Multi-word query
            params["query"] = " ".join(fake.words(nb=random.randint(2, 4)))

    # 50% chance to include topics
    if random.random() < 0.5:
        params["topics"] = ",".join(random.sample(SAMPLE_TOPICS, random.randint(1, 3)))

    # 30% chance to include source
    if random.random() < 0.3:
        params["source"] = random.choice(SAMPLE_SOURCES)

    # 20% chance to include verified filter
    if random.random() < 0.2:
        params["verified"] = random.choice([True, False])

    if random.random() < 0.1:
        params["limit"] = random.randint(1, 30)

    if random.random() < 0.1:
        params["offset"] = random.randint(0, 100)

    if random.random() < 0.1:
        params["startswith"] = fake.random_letter()
    return params


async def run_search_test(total_searches: int = 10000):
    client = RateLimitedClient()
    start_time = time.time()
    completed = 0
    errors = 0

    async with httpx.AsyncClient(timeout=30.0) as session:
        tasks = []
        for _ in range(total_searches):
            params = generate_random_params()
            task = asyncio.create_task(client.make_request(session, SEARCH_URL, params))
            tasks.append(task)

            # Process in batches of 100 to avoid overwhelming memory
            if len(tasks) >= 500:
                for completed_task in asyncio.as_completed(tasks):
                    try:
                        rich.print(await completed_task)
                        completed += 1
                    except Exception as e:
                        errors += 1
                        logger.error(f"Search failed: {e}")

                    if completed % 100 == 0:
                        elapsed = time.time() - start_time
                        rate = completed / elapsed
                        logger.info(
                            f"Completed {completed}/{total_searches} searches. "
                            f"Rate: {rate:.2f} requests/second. "
                            f"Errors: {errors}"
                        )
                tasks = []

        # Process remaining tasks
        if tasks:
            for completed_task in asyncio.as_completed(tasks):
                try:
                    rich.print(await completed_task)
                    completed += 1
                except Exception as e:
                    errors += 1
                    logger.error(f"Search failed: {e}")

    elapsed = time.time() - start_time
    logger.info(
        f"\nLoad test completed:"
        f"\nTotal searches: {total_searches}"
        f"\nCompleted: {completed}"
        f"\nErrors: {errors}"
        f"\nTotal time: {elapsed:.2f} seconds"
        f"\nAverage rate: {completed/elapsed:.2f} requests/second"
    )


if __name__ == "__main__":
    asyncio.run(run_search_test(1000))
