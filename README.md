# Party Roulette relay

Matchmaking relay for Party Roulette. Hosts register a lobby here, friends
see it in the Public Lobbies panel, and the relay forwards game messages
between the host and players. Everyone connects outbound, so no port
forwarding is needed anywhere.

## Deploy to Render (free)

1. Create a GitHub/GitLab repo and push this `relay/` folder to it.
2. Go to render.com -> New -> Blueprint -> pick the repo.
3. Render reads `render.yaml` and creates:
   - `party-roulette-relay` web service (the relay itself)
   - a `keep-awake` cron that pings `/health` every 10 min so the free
     tier websocket process never sleeps.
4. Wait a minute, then open `https://party-roulette-relay.onrender.com/health`
   (should show `ok`).

## Point the game at it

In the game (`game.py`) set:

    RELAY_URL = "wss://party-roulette-relay.onrender.com"

Then the lobby panel uses the live relay.

## Run locally for testing

    pip install -r requirements.txt
    python relay.py            # listens on 8765

    # in game.py use:
    RELAY_URL = "ws://localhost:8765"