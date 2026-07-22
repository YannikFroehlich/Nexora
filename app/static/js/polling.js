(() => {
    const start = ({url, interval = 1500, hiddenInterval = 10000, onData}) => {
        let etag = "";
        let failureCount = 0;
        let timeoutId;
        let stopped = false;
        let requestInFlight = false;

        const nextDelay = () => {
            if (document.hidden) {
                return hiddenInterval;
            }

            return Math.min(interval * (2 ** failureCount), 30000);
        };

        const schedule = (delay = nextDelay()) => {
            window.clearTimeout(timeoutId);

            if (!stopped) {
                timeoutId = window.setTimeout(poll, delay);
            }
        };

        const poll = async () => {
            if (stopped || requestInFlight) {
                return;
            }

            requestInFlight = true;

            try {
                const headers = {Accept: "application/json"};

                if (etag) {
                    headers["If-None-Match"] = etag;
                }

                const response = await fetch(url, {
                    cache: "no-store",
                    credentials: "same-origin",
                    headers,
                });

                if (response.status === 304) {
                    failureCount = 0;
                    return;
                }

                if (!response.ok) {
                    throw new Error(`Polling failed with status ${response.status}`);
                }

                etag = response.headers.get("ETag") || etag;
                await onData(await response.json());
                failureCount = 0;
            } catch {
                failureCount = Math.min(failureCount + 1, 5);
            } finally {
                requestInFlight = false;
                schedule();
            }
        };

        const handleVisibilityChange = () => {
            if (!document.hidden && !requestInFlight) {
                schedule(0);
            }
        };

        document.addEventListener("visibilitychange", handleVisibilityChange);
        poll();

        return () => {
            stopped = true;
            window.clearTimeout(timeoutId);
            document.removeEventListener("visibilitychange", handleVisibilityChange);
        };
    };

    window.NexoraPolling = {start};
})();
