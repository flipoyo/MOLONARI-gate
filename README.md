# Deploying the MOLONARI website v0.1.1

This file aims to explain the process of deploying the Molonari website.

## Overall architecture

The `molonari.io` website aims to provide an entry point for MOLONARI users. It features a landing page and a quickstart for understanding the project and starting to build a device.

Anticipating further customization (dataloggers API, remote MCMC, chatbot and code-hosting), we opted for a `Virtual Private Server` (VPS), which is basically a remotely-accessible computer that never turns off. The VPS is hosted by **LWS** and runs on Debian 12.

The website (html pages) is hosted by the VPS and built with WordPress. It should be accessible with the domain name (DNS) `molonari.io`, which was bought on **Namecheap**.

## Configuration

For now, we split the configuration process into three parts:
- configuring the DNS (molonari.io) with Namecheap: *see below*
- configuring the VPS with LWS: *see `server/vps_config.md`*
- configuring WordPress on the VPS: *see `website/wordpress_config.md`*

## Configuring the DNS

The domain name has to redirect requests to the VPS. To do so, we configure the domain list directly on Namecheap. IPv4 redirections are achieved with `A records`.
- Find the fixed IPv4 address of the VPS on the VPS provider website (`Panel` > `Serveurs` > `IPv4` on LWS)
- On the DNS provider's control panel, find the subdomains list (`Domain List` > `Advanced DNS` on Namecheap)
- Add a record:
    - type: `A record`
    - host: `@`
    - value: the VPS's IPv4
    - TTL: automatic

This process will redirect all requests to `http(s)://molonari.io/` to the VPS.

The `@` host can be changed to any value, for example `www` or `mysubdomain`. In that case, the DNS will forward requests addressed to `http(s)://www.molonari.io/` or `http(s)://mysubdomain.molonari.io/`.

- Important, to avoid certificate renewal failure, add a record:
    - type: `CNAME Record`
    - host: `www`
    - value: `molonari.io`
    - TTL: automatic
This maps: www.molonari.io → molonari.io 

**Checking:** We can verify that the DNS has been updated worldwide with the website [dnschecker.org](https://dnschecker.org/).

## Contributors

MOLONARI-gate is the website, server and deployment part of the MOLONARI1D project, held at Mines Paris - PSL.

- Nicolas Flipo manages the project and the infrastructure (VPS, website, deployment).
- Romain Lelaidier (MOLONARI2025) contributed to the website and server.
- Nabil El Houssein and Santiago Estrada (MOLONARI2026) contribute to its development.

Parts of the code, scripts and documentation were written with the assistance of large language models (Anthropic's Claude, through Claude Code), under the direction and review of the contributors above, who remain responsible for the content. LLM assistance is credited here, not in the commit messages.

## License

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

&copy; Contributors to MOLONARI-gate. Released under the [Apache License 2.0](LICENSE).

In plain words (a summary, not legal advice; the [LICENSE](LICENSE) text prevails):

- **You may** use, copy, modify, distribute and sell this software, including in commercial and closed-source projects, free of charge.
- **You must** keep the copyright notice and the license text, state the significant changes you made, and keep the `NOTICE` file if there is one.
- **Patents**: each contributor grants you a royalty-free license to the patents their contribution necessarily uses. If you sue anyone claiming the software infringes your patent, that license ends for you.
- **Contributions** you submit are under the same license, unless you state otherwise.
- **No trademark rights**: the license does not let you use the names or logos of the project or of Mines Paris - PSL.
- **No warranty and no liability**: the software is provided "as is"; the authors are not liable for damages from its use.
