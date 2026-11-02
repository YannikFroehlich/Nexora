(() => {
    // Anonymous, read-only Twitch chat: no token is needed to read a public channel.
    const IRC_URL = "wss://irc-ws.chat.twitch.tv:443";
    const ASSET_REFRESH_MS = 10 * 60 * 1000;
    const LEAVE_ANIMATION_MS = 450;
    const TEMPLATES = ["minimal", "glass", "neon"];
    const EVENT_TYPES = new Set([
        "sub",
        "resub",
        "subgift",
        "submysterygift",
        "giftpaidupgrade",
        "anongiftpaidupgrade",
        "primepaidupgrade",
        "raid",
        "announcement",
    ]);

    const numberValue = (value, fallback = 0) => {
        const parsed = Number.parseInt(value, 10);
        return Number.isFinite(parsed) ? parsed : fallback;
    };

    // Third-party APIs and IRC tags are untrusted: only ever load https images from them.
    const safeUrl = (value) => {
        try {
            const raw = String(value || "");
            const url = new URL(raw.startsWith("//") ? `https:${raw}` : raw);
            return url.protocol === "https:" ? url.href : "";
        } catch {
            return "";
        }
    };

    const fetchJson = async (url) => {
        try {
            const response = await fetch(url, {credentials: "omit"});
            return response.ok ? await response.json() : null;
        } catch {
            return null;
        }
    };

    // IRC message tags escape spaces, semicolons, backslashes and line breaks.
    const TAG_ESCAPES = {s: " ", ":": ";", "\\": "\\", r: "\r", n: "\n"};
    const unescapeTag = (value) => value.replace(/\\(.)/g, (_, char) => TAG_ESCAPES[char] ?? char);

    const parseIrcLine = (line) => {
        let rest = line;
        const tags = {};
        if (rest.startsWith("@")) {
            const end = rest.indexOf(" ");
            rest.slice(1, end).split(";").forEach((pair) => {
                const separator = pair.indexOf("=");
                if (separator === -1) tags[pair] = "";
                else tags[pair.slice(0, separator)] = unescapeTag(pair.slice(separator + 1));
            });
            rest = rest.slice(end + 1);
        }

        let prefix = "";
        if (rest.startsWith(":")) {
            const end = rest.indexOf(" ");
            prefix = rest.slice(1, end);
            rest = rest.slice(end + 1);
        }

        let trailing = "";
        const trailingAt = rest.indexOf(" :");
        if (trailingAt !== -1) {
            trailing = rest.slice(trailingAt + 2);
            rest = rest.slice(0, trailingAt);
        }

        const [command = "", ...params] = rest.split(" ").filter(Boolean);
        return {tags, prefix, command, params, trailing};
    };

    const sevenTvEmotes = (emoteSet) => (emoteSet?.emotes || []).map((emote) => ({
        name: emote.name,
        url: emote.data?.host?.url ? safeUrl(`${emote.data.host.url}/2x.webp`) : "",
        zeroWidth: Boolean((emote.flags & 1) || (emote.data?.flags & 256)),
    }));

    const bttvEmotes = (emotes) => (Array.isArray(emotes) ? emotes : []).map((emote) => ({
        name: emote.code,
        url: /^[a-f0-9]+$/i.test(emote.id || "") ? `https://cdn.betterttv.net/emote/${emote.id}/2x.webp` : "",
        zeroWidth: false,
    }));

    const ffzEmotes = (data, setIds) => {
        const sets = setIds ? setIds.map((id) => data?.sets?.[id]) : Object.values(data?.sets || {});
        return sets.flatMap((set) => set?.emoticons || []).map((emote) => {
            const urls = emote.animated || emote.urls || {};
            return {name: emote.name, url: safeUrl(urls["2"] || urls["1"]), zeroWidth: false};
        });
    };

    const loadEmotes = async (roomId, settings) => {
        const requests = [];
        // Order matters: later sources win name clashes, so 7TV beats BTTV beats FFZ,
        // and a channel's own emotes beat the global ones of the same service.
        if (settings.enable_ffz) {
            requests.push(fetchJson("https://api.frankerfacez.com/v1/set/global").then((data) => ffzEmotes(data, data?.default_sets || [])));
            if (roomId) requests.push(fetchJson(`https://api.frankerfacez.com/v1/room/id/${roomId}`).then((data) => ffzEmotes(data)));
        }
        if (settings.enable_bttv) {
            requests.push(fetchJson("https://api.betterttv.net/3/cached/emotes/global").then(bttvEmotes));
            if (roomId) {
                requests.push(fetchJson(`https://api.betterttv.net/3/cached/users/twitch/${roomId}`).then((data) => bttvEmotes([
                    ...(data?.channelEmotes || []),
                    ...(data?.sharedEmotes || []),
                ])));
            }
        }
        if (settings.enable_7tv) {
            requests.push(fetchJson("https://7tv.io/v3/emote-sets/global").then(sevenTvEmotes));
            if (roomId) requests.push(fetchJson(`https://7tv.io/v3/users/twitch/${roomId}`).then((data) => sevenTvEmotes(data?.emote_set)));
        }

        const emotes = new Map();
        (await Promise.all(requests)).flat().forEach((emote) => {
            if (emote.name && emote.url) emotes.set(emote.name, emote);
        });
        return emotes;
    };

    // ponytail: badge images come from the public api.ivr.fi mirror of Twitch's badge list;
    // switch to Helix chat/badges with an app token if that mirror ever goes away.
    const loadBadges = async (roomId) => {
        const responses = await Promise.all([
            fetchJson("https://api.ivr.fi/v2/twitch/badges/global"),
            roomId ? fetchJson(`https://api.ivr.fi/v2/twitch/badges/channel?id=${roomId}`) : null,
        ]);
        const badges = new Map();
        responses.forEach((sets) => (Array.isArray(sets) ? sets : []).forEach((set) => {
            (set.versions || []).forEach((version) => {
                const url = safeUrl(version.image_url_2x || version.image_url_1x);
                if (url) badges.set(`${set.set_id}/${version.id}`, {url, title: version.title || set.set_id});
            });
        }));
        return badges;
    };

    const createTwitchClient = ({onMessage, onStatus}) => {
        let socket = null;
        let channel = null;
        let retries = 0;
        let retryTimer;

        const connect = () => {
            window.clearTimeout(retryTimer);
            if (socket) {
                socket.onclose = null;
                socket.close();
                socket = null;
            }
            if (!channel) {
                onStatus("offline");
                return;
            }

            onStatus("connecting");
            const current = new WebSocket(IRC_URL);
            socket = current;
            current.onopen = () => {
                current.send("CAP REQ :twitch.tv/tags twitch.tv/commands");
                current.send("PASS SCHMOOPIIE");
                current.send(`NICK justinfan${Math.floor(10000 + Math.random() * 80000)}`);
                current.send(`JOIN #${channel}`);
            };
            current.onmessage = (event) => {
                String(event.data).split("\r\n").forEach((line) => {
                    if (!line) return;
                    const message = parseIrcLine(line);
                    if (message.command === "PING") {
                        current.send(`PONG :${message.trailing}`);
                        return;
                    }
                    if (message.command === "RECONNECT") {
                        current.close();
                        return;
                    }
                    if (message.command === "ROOMSTATE") {
                        retries = 0;
                        onStatus("live");
                    }
                    onMessage(message);
                });
            };
            current.onclose = () => {
                if (socket !== current) return;
                socket = null;
                onStatus("connecting");
                retryTimer = window.setTimeout(connect, Math.min(1000 * 2 ** retries, 30000));
                retries += 1;
            };
        };

        return {
            setChannel(nextChannel) {
                if (nextChannel === channel) return;
                channel = nextChannel;
                retries = 0;
                connect();
            },
        };
    };

    const element = (tagName, className, text) => {
        const node = document.createElement(tagName);
        if (className) node.className = className;
        if (text) node.textContent = text;
        return node;
    };

    const emoteImage = (url, name) => {
        const image = element("img", "chat-emote");
        image.src = url;
        image.alt = name;
        image.title = name;
        image.decoding = "async";
        return image;
    };

    // "25:0-4,12-16/1902:6-10" -> sorted code point ranges of native Twitch emotes.
    const twitchEmoteRanges = (tag) => (tag || "").split("/").flatMap((entry) => {
        const [id, positions = ""] = entry.split(":");
        if (!/^[\w-]+$/.test(id || "")) return [];
        return positions.split(",").map((range) => {
            const [start, end] = range.split("-").map((value) => numberValue(value, -1));
            return {id, start, end};
        }).filter((range) => range.start >= 0 && range.end >= range.start);
    }).sort((first, second) => first.start - second.start);

    const createChat = (overlay, initialState) => {
        const list = overlay.querySelector("[data-chat-messages]");
        const sources = new WeakMap();
        let settings = {...initialState.settings};
        let design = {};
        let roomId = "";
        let emotes = new Map();
        let badges = new Map();
        let assetKey = "";
        let assetsLoadedAt = 0;

        const fillText = (target, text, twitchEmotes) => {
            let lastEmote = null;

            const appendEmote = (image, zeroWidth) => {
                if (zeroWidth && lastEmote) {
                    if (!lastEmote.classList.contains("chat-emote-stack")) {
                        const stack = element("span", "chat-emote-stack");
                        lastEmote.replaceWith(stack);
                        stack.append(lastEmote);
                        lastEmote = stack;
                    }
                    lastEmote.append(image);
                    return;
                }
                target.append(image);
                lastEmote = image;
            };

            const appendWords = (words) => {
                words.split(/(\s+)/).forEach((word) => {
                    if (!word) return;
                    const emote = emotes.get(word);
                    if (emote) {
                        appendEmote(emoteImage(emote.url, word), emote.zeroWidth);
                        return;
                    }
                    target.append(word);
                    if (word.trim()) lastEmote = null;
                });
            };

            // Twitch counts emote positions in code points, not UTF-16 units.
            const chars = Array.from(text);
            let cursor = 0;
            twitchEmoteRanges(twitchEmotes).forEach(({id, start, end}) => {
                if (start < cursor || end >= chars.length) return;
                appendWords(chars.slice(cursor, start).join(""));
                const url = `https://static-cdn.jtvnw.net/emoticons/v2/${id}/default/dark/2.0`;
                appendEmote(emoteImage(url, chars.slice(start, end + 1).join("")), false);
                cursor = end + 1;
            });
            appendWords(chars.slice(cursor).join(""));
        };

        const buildItem = (message) => {
            const item = element("li", "chat-message");
            item.dataset.messageId = message.id || "";
            item.dataset.userId = message.userId || "";
            if (/^#[0-9a-f]{6}$/i.test(message.color || "")) {
                item.style.setProperty("--message-twitch-color", message.color);
            }
            if (message.action) item.classList.add("chat-message--action");
            if (message.system) {
                item.classList.add("chat-message--event");
                item.append(element("span", "chat-message__system", message.system));
            }
            if (message.text) {
                const author = element("span", "chat-message__author");
                if (settings.show_badges) {
                    message.badges.forEach((key) => {
                        const badge = badges.get(key);
                        if (!badge) return;
                        const image = element("img", "chat-message__badge");
                        image.src = badge.url;
                        image.alt = badge.title;
                        image.title = badge.title;
                        author.append(image);
                    });
                }
                author.append(element("span", "chat-message__name", message.displayName));
                const text = element("span", "chat-message__text");
                fillText(text, message.text, message.emotes);
                item.append(author, text);
            }
            sources.set(item, message);
            return item;
        };

        const newestFirst = () => overlay.dataset.direction === "top";

        const trim = () => {
            const items = Array.from(list.children);
            const excess = items.length - numberValue(settings.max_messages, 25);
            if (excess <= 0) return;
            (newestFirst() ? items.slice(-excess) : items.slice(0, excess)).forEach((item) => item.remove());
        };

        const fadeOut = (item) => {
            if (!item.isConnected) return;
            item.classList.add("chat-message--leaving");
            window.setTimeout(() => item.remove(), LEAVE_ANIMATION_MS);
        };

        // Re-render once emotes or badges arrive, without replaying the entry animation.
        const rerender = () => {
            Array.from(list.children).forEach((item) => {
                const message = sources.get(item);
                if (!message) return;
                const fresh = buildItem(message);
                fresh.style.animation = "none";
                item.replaceWith(fresh);
            });
        };

        const refreshAssets = async () => {
            const key = [roomId, settings.enable_7tv, settings.enable_bttv, settings.enable_ffz].join(":");
            if (key === assetKey && Date.now() - assetsLoadedAt < ASSET_REFRESH_MS) return;
            assetKey = key;
            assetsLoadedAt = Date.now();
            const [nextEmotes, nextBadges] = await Promise.all([loadEmotes(roomId, settings), loadBadges(roomId)]);
            if (key !== assetKey) return;
            emotes = nextEmotes;
            badges = nextBadges;
            rerender();
        };

        const add = (message) => {
            const item = buildItem(message);
            if (newestFirst()) list.prepend(item);
            else list.append(item);
            trim();
            const lifetime = numberValue(settings.message_lifetime_seconds);
            if (lifetime > 0) window.setTimeout(() => fadeOut(item), lifetime * 1000);
            refreshAssets();
        };

        const fromIrc = ({tags, prefix, trailing}) => {
            const login = (tags.login || prefix.split("!")[0] || "").toLowerCase();
            const action = /^\u0001ACTION (.*)\u0001$/s.exec(trailing);
            return {
                id: tags.id,
                userId: tags["user-id"],
                login,
                displayName: tags["display-name"] || login,
                color: tags.color,
                badges: (tags.badges || "").split(",").filter(Boolean),
                text: action ? action[1] : trailing,
                emotes: tags.emotes,
                action: Boolean(action),
            };
        };

        const isHidden = (message) => (
            (settings.hidden_users || []).includes(message.login)
            || (settings.hide_commands && message.text.startsWith("!"))
        );

        const handle = (irc) => {
            const {command, tags} = irc;
            if (command === "ROOMSTATE" && /^\d+$/.test(tags["room-id"] || "")) {
                roomId = tags["room-id"];
                refreshAssets();
            } else if (command === "PRIVMSG") {
                const message = fromIrc(irc);
                if (!isHidden(message)) add(message);
            } else if (command === "USERNOTICE" && settings.show_events && EVENT_TYPES.has(tags["msg-id"])) {
                add({...fromIrc(irc), system: tags["system-msg"] || ""});
            } else if (command === "CLEARMSG") {
                Array.from(list.children)
                    .filter((item) => item.dataset.messageId === tags["target-msg-id"])
                    .forEach((item) => item.remove());
            } else if (command === "CLEARCHAT") {
                // Without a target user the whole chat was cleared by a moderator.
                const userId = tags["target-user-id"];
                Array.from(list.children)
                    .filter((item) => !userId || item.dataset.userId === userId)
                    .forEach((item) => item.remove());
            }
        };

        const applySettings = (nextSettings = {}) => {
            settings = {...settings, ...nextSettings};
            trim();
            refreshAssets();
        };

        const applyDesign = (nextDesign = {}) => {
            const previousDirection = overlay.dataset.direction;
            design = {...design, ...nextDesign};
            overlay.classList.remove(...TEMPLATES.map((template) => `chat-overlay--${template}`));
            overlay.classList.add(`chat-overlay--${TEMPLATES.includes(design.template) ? design.template : "glass"}`);
            overlay.dataset.layout = design.layout || "inline";
            overlay.dataset.direction = design.direction || "bottom";
            overlay.dataset.animation = design.animation || "slide";
            overlay.dataset.shadow = String(design.shadow_enabled !== false);
            overlay.dataset.twitchColors = String(design.use_twitch_name_colors !== false);
            if (previousDirection && previousDirection !== overlay.dataset.direction) {
                list.append(...Array.from(list.children).reverse());
            }

            const properties = {
                "--chat-background": design.background_rgba,
                "--chat-text": design.text_color,
                "--chat-accent": design.accent_color,
                "--chat-name": design.name_color,
                "--chat-border": design.border_color,
                "--chat-border-width": `${numberValue(design.border_width, 1)}px`,
                "--chat-radius": `${numberValue(design.corner_radius, 14)}px`,
                "--chat-font-size": `${numberValue(design.font_size, 20)}px`,
                "--chat-emote-size": `${numberValue(design.emote_size, 28)}px`,
                "--chat-gap": `${numberValue(design.message_gap, 8)}px`,
            };
            Object.entries(properties).forEach(([name, value]) => {
                if (value) overlay.style.setProperty(name, value);
            });
            if (["font_family", "font_url", "logo_url", "background_image_url"].some((key) => key in nextDesign)) {
                window.NexoraBranding?.apply(overlay, design);
            }
        };

        applyDesign(initialState.design);
        refreshAssets();
        return {add, handle, applySettings, applyDesign};
    };

    const overlay = document.querySelector("[data-chat-overlay]");
    const initialStateNode = document.getElementById("chat-initial-state");
    if (!overlay || !initialStateNode) return;

    const initialState = JSON.parse(initialStateNode.textContent);
    const chat = createChat(overlay, initialState);
    const statusNode = document.querySelector("[data-chat-status]");
    const client = createTwitchClient({
        onMessage: chat.handle,
        onStatus: (status) => {
            if (!statusNode) return;
            statusNode.dataset.state = status;
            statusNode.textContent = statusNode.dataset[`status${status[0].toUpperCase()}${status.slice(1)}`] || "";
        },
    });
    client.setChannel(initialState.channel || "");

    const source = document.querySelector("[data-chat-source]");
    if (source && window.NexoraPolling) {
        window.NexoraPolling.start({
            url: source.dataset.stateUrl,
            interval: 5000,
            hiddenInterval: 15000,
            onData: (state) => {
                chat.applySettings(state.settings);
                chat.applyDesign(state.design);
                client.setChannel(state.channel || "");
            },
        });
    }

    const editor = document.querySelector("[data-chat-editor]");
    if (!editor) return;

    const form = editor.querySelector("[data-chat-form]");
    const fieldValue = (name, fallback = "") => {
        const field = form?.elements.namedItem(name);
        return field ? field.value : fallback;
    };
    const checked = (name) => Boolean(form?.elements.namedItem(name)?.checked);

    // Mirrors ChatOverlayForm.clean_channel so the preview joins the channel that will be saved.
    const channelFromForm = () => fieldValue("channel")
        .trim()
        .toLowerCase()
        .replace(/^(https?:\/\/)?(www\.|m\.)?twitch\.tv\//, "")
        .replace(/\/+$/, "")
        .replace(/^[#@]+/, "");

    const settingsFromForm = () => ({
        max_messages: numberValue(fieldValue("max_messages", 25), 25),
        message_lifetime_seconds: numberValue(fieldValue("message_lifetime_seconds", 0)),
        show_badges: checked("show_badges"),
        show_events: checked("show_events"),
        hide_commands: checked("hide_commands"),
        hidden_users: fieldValue("hidden_users").toLowerCase().split(/[\s,]+/).map((login) => login.replace(/^@/, "")).filter(Boolean),
        enable_7tv: checked("enable_7tv"),
        enable_bttv: checked("enable_bttv"),
        enable_ffz: checked("enable_ffz"),
    });

    const designFromForm = () => {
        const color = fieldValue("background_color", "#0b1020");
        const opacity = Math.min(Math.max(numberValue(fieldValue("background_opacity", 72)), 0), 100);
        const [red, green, blue] = [1, 3, 5].map((offset) => Number.parseInt(color.slice(offset, offset + 2), 16) || 0);
        return {
            template: fieldValue("design_template", "glass"),
            layout: fieldValue("message_layout", "inline"),
            direction: fieldValue("message_direction", "bottom"),
            animation: fieldValue("animation", "slide"),
            background_rgba: `rgba(${red}, ${green}, ${blue}, ${(opacity / 100).toFixed(2)})`,
            text_color: fieldValue("text_color", "#f8fafc"),
            accent_color: fieldValue("accent_color", "#8b5cf6"),
            use_twitch_name_colors: checked("use_twitch_name_colors"),
            name_color: fieldValue("name_color", "#a78bfa"),
            border_color: fieldValue("border_color", "#a78bfa"),
            border_width: fieldValue("border_width", 1),
            corner_radius: fieldValue("corner_radius", 14),
            font_size: fieldValue("font_size", 20),
            emote_size: fieldValue("emote_size", 28),
            message_gap: fieldValue("message_gap", 8),
            shadow_enabled: checked("shadow_enabled"),
        };
    };

    let channelTimer;
    const updatePreview = () => {
        chat.applySettings(settingsFromForm());
        chat.applyDesign(designFromForm());
        window.clearTimeout(channelTimer);
        channelTimer = window.setTimeout(() => client.setChannel(channelFromForm()), 700);
    };
    if (form) {
        form.addEventListener("input", updatePreview);
        form.addEventListener("change", updatePreview);
        form.addEventListener("nexora:editor-restore", updatePreview);
    }

    // Sample messages show badges, a native Twitch emote and one global emote per service.
    const testButton = editor.querySelector("[data-chat-test-message]");
    const demoTexts = (testButton?.dataset.demoTexts || "").split("|").filter(Boolean);
    const demoMessages = [
        {displayName: "Nexora", color: "#a78bfa", badges: ["broadcaster/1"], suffix: " Kappa"},
        {displayName: "ModMaxi", color: "#22c55e", badges: ["moderator/1", "subscriber/0"], suffix: " EZ"},
        {displayName: "PixelPia", color: "#f97316", badges: ["vip/1"], suffix: " :tf:"},
        {displayName: "LurkerLuca", color: "#38bdf8", badges: ["premium/1"], suffix: " LilZ"},
    ];
    let demoIndex = 0;
    const addDemoMessage = () => {
        const demo = demoMessages[demoIndex % demoMessages.length];
        const text = `${demoTexts[demoIndex % Math.max(demoTexts.length, 1)] || "Hello chat!"}${demo.suffix}`;
        const kappaAt = text.indexOf("Kappa");
        chat.add({
            id: `demo-${demoIndex}`,
            userId: "",
            login: demo.displayName.toLowerCase(),
            displayName: demo.displayName,
            color: demo.color,
            badges: demo.badges,
            text,
            emotes: kappaAt === -1 ? "" : `25:${kappaAt}-${kappaAt + 4}`,
            action: false,
        });
        demoIndex += 1;
    };
    testButton?.addEventListener("click", addDemoMessage);
    demoMessages.forEach(addDemoMessage);
    updatePreview();

    const toast = document.querySelector("[data-copy-toast]");
    let toastTimer;
    document.addEventListener("click", async (event) => {
        const copyButton = event.target.closest("[data-copy-url]");
        if (!copyButton) return;
        try {
            await navigator.clipboard.writeText(copyButton.dataset.copyUrl);
            if (toast) {
                toast.hidden = false;
                window.clearTimeout(toastTimer);
                toastTimer = window.setTimeout(() => { toast.hidden = true; }, 2200);
            }
        } catch {
            window.prompt(copyButton.textContent.trim(), copyButton.dataset.copyUrl);
        }
    });

    document.addEventListener("submit", (event) => {
        const deleteForm = event.target.closest("[data-confirm-delete]");
        if (deleteForm && !window.confirm(deleteForm.dataset.confirmDelete)) {
            event.preventDefault();
        }
    });
})();
