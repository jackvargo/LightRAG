Below is a proven pattern that keeps **one Traefik edge-proxy running in its own stack** and lets every other compose/Portainer stack “plug-in” to it via a shared, external, attachable Docker network. This layout isolates restarts, scales cleanly, and leaves you free to version/replace any back-end service without ever touching the proxy.

## Why a single Traefik stack is preferable

* **Centralised TLS / ACME** – one place to issue and renew certificates; avoids rate-limit collisions you would hit if every stack ran its own proxy. ([doc.traefik.io][1], [blog.kilian.io][2])
* **Lifecycle isolation** – you can `docker compose down lightrag` and only that route returns 502; every other app keeps flowing through Traefik. ([reddit.com][3])
* **Lower operational surface** – only one container exposes ports :80/443 to the host firewall, so DNAT / fail2ban rules stay simple. ([hackernoon.com][4])
* **Native discovery** – the Docker provider reads labels on *any* container connected to the proxy’s network, even if that container lives in another compose file or Portainer stack. ([doc.traefik.io][5], [doc.traefik.io][1])

Running a proxy *inside* every stack duplicates all of the above, forces you to juggle port mappings, and usually explodes Let’s Encrypt rate-limits. For most home-lab / pre-prod clusters, a single Traefik instance is therefore canonical. ([reddit.com][6], [reddit.com][7])

## Network topology

```bash
# one-time on the host (or in Portainer > Networks)
docker network create --attachable traefik_proxy
```

*The attachable flag lets other, non-swarm containers join at runtime.* ([community.traefik.io][8], [stackoverflow.com][9])

### Traefik stack (its own `docker-compose.yml`)

```yaml
version: "3.9"
services:
  traefik:
    image: traefik:v3.4
    command:
      - "--providers.docker=true"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.le.acme.httpchallenge=true"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro   # see security note
      - ./acme.json:/acme.json
    networks:
      - traefik_proxy
    ports:
      - "80:80"
      - "443:443"
networks:
  traefik_proxy:
    external: true
```

### Application stack (example: LightRAG)

```yaml
version: "3.9"
services:
  lightrag:
    image: ghcr.io/…/lightrag:latest
    networks:
      - traefik_proxy
      - internal
    labels:
      - traefik.enable=true
      - traefik.http.routers.lightrag.rule=Host(`rag.lab.local`)
      - traefik.http.routers.lightrag.entrypoints=websecure
      - traefik.http.routers.lightrag.tls.certresolver=le
networks:
  traefik_proxy:
    external: true       # join the shared network
  internal:              # service-local network
```

Repeat the same two-line `external: true` stanza in every other compose/Portainer stack (n8n, Supabase, Open WebUI, etc.).

Traefik instantly “sees” new containers because the Docker provider watches the daemon socket and filters by network-membership and labels. ([doc.traefik.io][5], [jon.sprig.gs][10])

## Using Portainer

1. **Create the external network** once under *Settings → Networks → +Add network* and tick *Attachable*.
2. Deploy Traefik as a standalone stack (or copy an existing compose file into Portainer).
3. For every new stack choose “*Use existing network* → `traefik_proxy`”. Portainer will inject the correct `external: true` boiler-plate for you. ([reddit.com][11], [docs.portainer.io][12])

## Updating without collateral outages

* **Traefik itself** – pull a new image and `docker compose up -d`; because a new container joins exactly the same network and acquires the same labels, active connections are handed over in milliseconds. ([reddit.com][3])
* **Back-end services** – restart or rebuild any stack; only its routes are impacted. Other routers remain mounted because Traefik’s config cache is independent per router. ([community.traefik.io][13])

For near-zero downtime on heavy upgrades, spin a *second* Traefik instance, connect it to `traefik_proxy`, prime certificates via the same volume (or an S3-backed KV store), then drain the first instance. ([community.traefik.io][14])

## Security hardening tips

| Risk                                       | Mitigation                                                                                                                                               |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Exposing `/var/run/docker.sock` read-write | Use **\[Docker Socket-Proxy]** or mount it read-only plus `providers.docker.swarmMode=true` in future if you migrate to Swarm. ([forums.docker.com][15]) |
| Wild-card HTTP → HTTPS redirect loops      | Add a `web` entrypoint on :80 with a redirect-scheme middleware. ([docs.docker.com][16])                                                                 |
| Accidental public exposure                 | Attach only the required app port to `traefik_proxy`; keep db/cache services on private networks. ([reddit.com][7])                                      |

## When a per-stack proxy *does* make sense

* You need *hard* multi-tenant isolation (e.g., client A must never sniff headers belonging to client B).
* Each stack must be self-contained and deployable onto hosts that are not allowed to share a global Docker network.
* You want to experiment with very different edge tech (e.g., Caddy for one stack, Traefik for another).

Outside those edge-cases, a single Traefik gateway + shared external network remains the most maintainable approach for a Portainer-managed, compose-centric home-lab. ([community.traefik.io][17])

[1]: https://doc.traefik.io/traefik/routing/providers/docker/?utm_source=chatgpt.com "Traefik Docker Routing Documentation"
[2]: https://blog.kilian.io/server-setup/?utm_source=chatgpt.com "Server Setup with traefik and docker-compose | blog.kilian.io"
[3]: https://www.reddit.com/r/Traefik/comments/137yc75/any_way_to_reduce_proxy_downtime_during_docker/?utm_source=chatgpt.com "Any way to reduce proxy downtime during docker container updates"
[4]: https://hackernoon.com/exploring-traefik-a-reverse-proxy-for-docker?utm_source=chatgpt.com "Exploring Traefik: A Reverse Proxy for Docker - HackerNoon"
[5]: https://doc.traefik.io/traefik/user-guides/docker-compose/basic-example/?utm_source=chatgpt.com "Docker Compose example - Traefik Labs documentation"
[6]: https://www.reddit.com/r/docker/comments/p10shc/how_to_set_up_a_single_reverse_proxy_for_multiple/?utm_source=chatgpt.com "How to set up a single reverse proxy for multiple docker-compose ..."
[7]: https://www.reddit.com/r/docker/comments/1bp9mgy/is_there_point_to_creating_various_docker/?utm_source=chatgpt.com "Is there point to creating various docker networks if the reverse proxy ..."
[8]: https://community.traefik.io/t/traefik-proxy-multiple-networks-application-single/22415?utm_source=chatgpt.com "Traefik proxy multiple networks, application single"
[9]: https://stackoverflow.com/questions/71034142/is-it-possible-to-create-an-external-attachable-overlay-network-from-within-a-do?utm_source=chatgpt.com "Is it possible to create an external attachable overlay network from ..."
[10]: https://jon.sprig.gs/blog/post/3254?utm_source=chatgpt.com "A Quick Guide to setting up Traefik on a single Docker node inside ..."
[11]: https://www.reddit.com/r/portainer/comments/12z8ctr/how_to_setup_traefik_to_access_containers_in/?utm_source=chatgpt.com "How to setup traefik to access containers in different stacks? (docker ..."
[12]: https://docs.portainer.io/advanced/reverse-proxy/traefik?utm_source=chatgpt.com "Deploying Portainer behind Traefik Proxy"
[13]: https://community.traefik.io/t/how-to-move-to-new-server-with-zero-downtime/19309?utm_source=chatgpt.com "How to move to new server with zero downtime? - Traefik v2"
[14]: https://community.traefik.io/t/setting-up-traefik-for-docker-and-external-services/14151?utm_source=chatgpt.com "Setting up traefik for Docker and external services"
[15]: https://forums.docker.com/t/how-to-let-traefik-reverse-proxy-services-that-are-outside-of-docker-that-running-traefik/126041?utm_source=chatgpt.com "How to let traefik reverse-proxy services that are outside of docker ..."
[16]: https://docs.docker.com/guides/traefik/?utm_source=chatgpt.com "HTTP routing with Traefik - Docker Docs"
[17]: https://community.traefik.io/t/docker-swarm-docker-standalone-together/18398?utm_source=chatgpt.com "Docker Swarm & Docker Standalone together?"
