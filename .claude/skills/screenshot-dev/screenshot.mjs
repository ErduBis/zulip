#!/usr/bin/env node
// Log in to the development server as a test user and take a screenshot.
// Usage: see SKILL.md next to this file.

import {createRequire} from "node:module";
import path from "node:path";
import {parseArgs} from "node:util";

const repo_root = path.resolve(import.meta.dirname, "../../..");
const require = createRequire(path.join(repo_root, "package.json"));
const puppeteer = require("puppeteer");

const {values: options} = parseArgs({
    options: {
        user: {type: "string", default: "sunwukong@zulip.com"},
        path: {type: "string", default: "/"},
        out: {type: "string", default: `/tmp/screenshot-dev-${Date.now()}.png`},
        lang: {type: "string"},
        width: {type: "string", default: "1280"},
        height: {type: "string", default: "800"},
        "wait-for": {type: "string"},
        element: {type: "string"},
        "full-page": {type: "boolean", default: false},
        dark: {type: "boolean", default: false},
    },
});

const base_url = "http://localhost:9991";

async function json_request(page, method, url, params) {
    // Read the token from the cookie: not every page has a CSRF form
    // field (for example /stats), and settings are restored from
    // whatever page the screenshot was taken on.
    const cookies = await page.cookies();
    const csrf_token = cookies.find((cookie) => cookie.name === "csrftoken")?.value;
    if (csrf_token === undefined) {
        throw new Error("No csrftoken cookie; is the user logged in?");
    }
    return await page.evaluate(
        async (method, url, params, csrf_token) => {
            const response = await fetch(url, {
                method,
                headers: {"X-CSRFToken": csrf_token},
                body: new URLSearchParams(params),
            });
            if (!response.ok) {
                throw new Error(`${method} ${url} failed: ${await response.text()}`);
            }
            return await response.json();
        },
        method,
        url,
        params,
        csrf_token,
    );
}

async function get_user_settings(page) {
    const response = await json_request(page, "POST", "/json/register", {
        fetch_event_types: JSON.stringify(["user_settings"]),
    });
    return response.user_settings;
}

async function patch_settings(page, settings) {
    await json_request(page, "PATCH", "/json/settings", settings);
}

async function load_app(page) {
    // Reload first so the temporary language and theme take effect: going to
    // a path that only differs by its hash would keep the already loaded page.
    await page.reload({waitUntil: "networkidle2"});
    await page.waitForSelector("#left-sidebar", {visible: true, timeout: 60_000});
    if (options.path !== "/") {
        await page.goto(`${base_url}${options.path}`, {waitUntil: "networkidle2"});
        // Let overlays such as settings finish their opening animation.
        await new Promise((resolve) => setTimeout(resolve, 500));
    }
}

const browser = await puppeteer.launch({args: ["--no-sandbox", "--disable-setuid-sandbox"]});
// Settings changed for the screenshot, with the values to restore afterwards.
const restore = {};
let page;
try {
    page = await browser.newPage();
    await page.setViewport({width: Number(options.width), height: Number(options.height)});

    await page.goto(`${base_url}/devlogin/`, {waitUntil: "networkidle2"});
    await Promise.all([
        page.waitForNavigation({waitUntil: "networkidle2"}),
        page.click(`[name="direct_email"][value="${options.user}"]`),
    ]);
    await page.waitForSelector("#left-sidebar", {visible: true, timeout: 60_000});

    const temporary_settings = {};
    if (options.lang !== undefined) {
        temporary_settings.default_language = options.lang;
    }
    if (options.dark) {
        temporary_settings.color_scheme = "2";
    }
    if (Object.keys(temporary_settings).length > 0) {
        const original = await get_user_settings(page);
        for (const key of Object.keys(temporary_settings)) {
            restore[key] = String(original[key]);
        }
        await patch_settings(page, temporary_settings);
    }

    await load_app(page);
    if (options["wait-for"] !== undefined) {
        await page.waitForSelector(options["wait-for"], {visible: true, timeout: 30_000});
    }

    if (options.element === undefined) {
        await page.screenshot({path: options.out, fullPage: options["full-page"]});
    } else {
        const element = await page.waitForSelector(options.element, {visible: true});
        await element.screenshot({path: options.out});
    }
    console.log(options.out);
} finally {
    if (page !== undefined && Object.keys(restore).length > 0) {
        await patch_settings(page, restore);
    }
    await browser.close();
}
