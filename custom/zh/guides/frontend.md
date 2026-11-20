# 前端开发指南

面向前端角色（负责 `web/`、`templates/`）。`DEVELOPMENT.md` 和 `.claude/rules/frontend.md`、
`.claude/rules/css.md` 里的规则照常适用，这里不重复，只补充在 Zulip 13.2 上做定制界面时要知道的东西。
动手前先 `git grep` 找一个最像的现有功能，照着它的文件和写法来。

## 代码在哪里

| 路径                           | 内容                                                                                                  |
| ------------------------------ | ----------------------------------------------------------------------------------------------------- |
| `web/src/*.ts`                 | 应用代码，ES 模块。只有 `ui_init.js`、`server_events.js`、`server_events_dispatch.js` 仍是 JavaScript |
| `web/src/portico/`             | 未登录页面（登录、注册等）的代码                                                                      |
| `web/templates/**/*.hbs`       | Handlebars 模板，浏览器端渲染。通用组件在 `components/`，浮出菜单在 `popovers/`，设置页在 `settings/` |
| `web/styles/*.css`             | 应用样式，按界面区域分文件；未登录页样式在 `web/styles/portico/`                                      |
| `web/icons/*.svg`              | 图标源文件，构建时编译成图标字体                                                                      |
| `web/images/`                  | 经 webpack 打包的图片                                                                                 |
| `templates/**/*.html`          | Jinja2 服务端模板；应用外壳是 `templates/zerver/app/index.html`                                       |
| `web/tests/`、`web/e2e-tests/` | node 单元测试、Puppeteer 端到端测试                                                                   |
| `web/webpack.assets.json`      | 各页面的 bundle 入口（仅开发环境的页面在 `web/webpack.dev-assets.json`）                              |

- 新模块、新 CSS 文件必须能从入口引用到才会被加载：应用内用的在 `web/src/bundles/app.ts` 里 import；
  应用和未登录页都要用的放 `web/src/bundles/common.ts`；独立页面在 `webpack.assets.json` 加入口，
  Jinja2 模板里写 `{% set entrypoint = "入口名" %}`（`templates/zerver/base.html` 用
  `webpack_entry(entrypoint)` 注入 JS/CSS）。
- 开发服务器热更新：改 CSS 立即生效，改 `.ts`/`.hbs` 浏览器自动刷新。
- 浏览器控制台调试（仅开发环境）：`require("./src/people")` 可拿到任意模块
  （`web/debug-require-webpack-plugin.ts`）；全局 `zulip_test` 见 `web/src/zulip_test.ts`。只用于调试。

## 初始状态与实时事件

1. **page_params**：服务端把页面参数放在 `#page-params`，`web/src/base_page_params.ts` 用 zod 解析
   （首页参数对应 `zerver/lib/home.py` 的 `build_page_params_for_home_page_load`）。
   应用代码从 `web/src/page_params.ts` 导入。
2. **state_data**：`/json/register` 返回的初始数据，通常随 `page_params.state_data` 一起下发；
   访客和客户端触发的重载时 `page_params.no_event_queue` 为真，由 `ui_init.js` 自己 POST
   `/json/register`（参数要和 `zerver/lib/home.py` 保持一致）。
3. `state_data.ts` 的 `state_data_schema` 用 `split_state_data_schema` 把整份数据按模块切块，
   `ui_init.initialize_everything` 把每块交给对应模块的 `initialize`。
   - **zod 的 object 会丢弃没声明的字段**：后端新增的字段必须加进对应块的 schema，否则前端拿不到也不报错。
     组织设置 → `realm_schema`（键带 `realm_` 前缀）；用户设置 → `user_settings.ts` 的
     `user_settings_schema`；当前用户 → `current_user_schema`。
   - 读取：`import {current_user, realm} from "./state_data.ts"`、`import {user_settings} from "./user_settings.ts"`。
   - 消息不在初始状态里，由 `message_fetch.ts` 另外获取；尚未获取的消息的相关事件会被丢弃。
4. **事件**：`server_events.js` 长轮询 `/json/events`，交给
   `server_events_dispatch.dispatch_normal_event(event)` 按 `event.type` 分发。
   - 自己发起的修改也会以事件回来。界面更新写在事件处理里；AJAX 的 `success` 只做本次操作的反馈
     （显示勾号、关闭弹窗），这样多个标签页、多个用户看到的结果一致。
   - `realm` 的 `update` 事件：只有列在 `realm_settings` 对象里的属性才会写回 `realm`。
     新设置必须加一行（没有额外界面要更新就写 `noop`）；设置页表单由 `settings_org.sync_realm_settings` 同步。
   - `user_settings` 事件同理：属性必须出现在该 `case` 里的某个列表中
     （通知类在 `settings_config.all_notification_settings`）。
   - 网页端自己调用 `/json/register` 时只请求 `server_event_types.ts` 里 `FETCH_EVENT_TYPES` 列出的类型；
     新数据类型的初始状态要让前端拿到，就加进这个列表。

## 调用后端接口

- 用 `channel.ts` 的 `get`/`post`/`patch`/`put`/`del`：`channel.post({url: "/json/...", data, success, error})`。
  网页端走 `/json/` 前缀。
- `data` 按表单编码发送：后端声明为 `Json[...]` 的参数（布尔、数字、列表、对象）要先 `JSON.stringify`。
- 响应先用 zod 解析再用：`const {id} = z.object({id: z.number()}).parse(data);`
- 错误展示用 `ui_report.error(...)`、`channel.xhr_error_message(...)`；对话框里提交用
  `dialog_widget.submit_api_request(...)`，它负责转圈、出错提示和关闭。

## 加一个设置项（前端部分）

以布尔组织设置 `realm_require_unique_names` 为样板（`git grep require_unique_names web/` 能看到全部落点）：

1. `state_data.ts` 的 `realm_schema` 加 `realm_<name>: z.boolean()`。
2. 在 `web/templates/settings/organization_*_admin.hbs` 合适的小节里加
   `{{> settings_checkbox setting_name="realm_<name>" prefix="id_" is_checked=realm_<name> label=admin_settings_label.realm_<name>}}`。
   非复选框控件要写 `data-setting-widget-type`。控件 id 必须是 `id_<setting_name>` 且带 `prop-element` 类：
   保存/放弃逻辑靠 `settings_components.extract_property_name` 从 id 取属性名。
3. `admin.ts`：`admin_settings_label` 加标签（`$t`），`build_page` 的 `options` 加当前值。
4. `server_events_dispatch.js` 的 `realm_settings` 加一行。
5. `web/tests/lib/example_realm.cjs` 加默认值。
6. 手动检查：保存和「放弃更改」都正常；依赖其他设置的控件显隐正确；开两个窗口看实时同步；
   各小节的保存互不影响。

用户个人设置对应 `settings_preferences.ts`、`settings_notifications.ts` 和
`web/templates/settings/preferences_*.hbs`。新增设置页分区：在 `settings_overlay.hbs` 加带
`data-section` 的侧栏项，并在 `settings_sections.initialize` 里注册加载函数。

## 模板

**Handlebars**（`import render_foo from "../templates/foo.hbs"`，`render_foo(context)` 返回 HTML 字符串）。
编译选项在 `web/webpack.config.ts`，有三条容易踩坑：

- `strict`：`{{foo}}` 引用上下文里不存在的字段会直接抛错（`{{#if foo}}` 不会）。上下文要给全，可选值用 `#if` 包住。
- `knownHelpersOnly`：只能用 `web/src/templates.ts` 注册且列在 `knownHelpers` 里的 helper：
  `eq`、`and`、`or`、`not`、`t`、`tr`、`rendered_markdown`、`numberFormat`、`list_each`、
  `tooltip_hotkey_hints`、`popover_hotkey_hints`、`map_entries`、`object_entries`、`object_values`。
- `explicitPartialContext`：partial 不继承调用方上下文，要写 `{{> foo .}}` 或 `{{> foo key=value}}`。
  partial 路径相对当前模板所在目录，如 `{{> ../components/action_button ...}}`。

其他规则：

- `{{var}}` 自动转义；`{{{var_html}}}` 不转义，变量名必须以 `_html` 结尾（`tools/check-templates` 检查），
  只放可信 HTML：模板渲染结果、`$t_html` 结果；服务端渲染的消息内容用 `{{rendered_markdown content}}`。
- 复杂 DOM 用模板生成。不要把 HTML 字符串直接传给 `.append()`（eslint `no-jquery/no-append-html`），
  用 `$(render_foo(...))` 或 `ui_util.parse_html(...)`。
- `style=` 只用于动态值（如频道颜色），其余样式写进 CSS。

**Jinja2**（`templates/`）：上下文来自 `zerver/context_processors.py` 的 `zulip_default_context` 和视图里的
`render(...)` 调用（`git grep '模板路径' '*.py'` 可找到）。需要新的上下文变量时找后端。

## 翻译标记

TypeScript（`web/src/i18n.ts`）：

```ts
$t({defaultMessage: "Channel settings"});
$t({defaultMessage: "Invite {name}?"}, {name}); // 纯文本，不转义：用 .text() 或交给模板转义
$t_html({defaultMessage: "<b>{count}</b> new replies."}, {count}); // 值会被转义，结果可当 HTML 用
$t_html(
    {defaultMessage: "Go to <z-link>settings</z-link>."},
    {"z-link": (content_html) => `<a href="#settings">${content_html.join("")}</a>`},
);
$t({defaultMessage: "{N, plural, one {# message} other {# messages}}"}, {N: count});
```

Handlebars：

```hbs
{{t "Channel settings" }}
{{t "Invite {full_name}?" }}  {{! 变量取自当前上下文（字符串、数字、日期） }}
{{> settings_checkbox label=(t "Require unique names") }}
{{#tr}}Your plan is <b>{plan_name}</b>.{{/tr}}
{{#tr}}Read the <z-link>guide</z-link>.{{#*inline "z-link"}}<a href="/help/">{{> @partial-block}}</a>{{/inline}}{{/tr}}
```

Jinja2：

```jinja
{{ _("Log in") }}
{% trans %}Check your email ({{ email }}).{% endtrans %}
```

- `defaultMessage` 和 `{{t}}` 的参数必须是字面量，不能传变量：提取工具只认字面量（TS 里 eslint 也会检查）。
- 译文里能直接写的标签只有 `b code em i kbd p strong`，且不带属性（`i18n.ts` 的 `default_html_elements`）；
  链接等复杂标记用 `<z-...>` 自定义标签。`{{#tr}}` 块里不能出现 `{{var}}` 或 `{{#if}}`，变量用单花括号。
- 整句标记，不拼接；句末标点放进字符串。复数用 ICU 语法，能用「图标 + 数字」代替的就不写复数句。
  列表用 `util.format_array_as_list(items, "long", "conjunction")`。
- 大小写用句首大写：「Channel settings」而不是「Channel Settings」；专有名词大写；URL、HTTP 等用标准写法。
  界面文字说 organization，不说 realm（会被拦下）。检查：`./tools/check-capitalization`
  （它只重新生成被 git 忽略的 `locale/en/`）。
- 新文字在集成与品牌更新翻译文件之前，中文界面显示英文原文，属正常现象。
- 不同语言文字长度差别很大，按钮、标签不写死宽度。

## 现有组件（先找能复用的）

| 需要               | 用什么                                                                                                                                                                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 对话框、表单弹窗   | `dialog_widget.launch({modal_title_text, modal_content_html, on_click, ...})`；确认框 `confirm_dialog.launch`；底层 `modals.ts`                                                                                                                         |
| 浮出菜单           | `popover_menus.register_popover_menu(selector, tippy_props)`，`onHidden` 里调用 `instance.destroy()`；模板放 `web/templates/popovers/`                                                                                                                  |
| 提示气泡           | 元素加 `tippy-zulip-tooltip` 类和 `data-tippy-content="{{t '...' }}"`；延迟版 `tippy-zulip-delayed-tooltip`；富内容用 `data-tooltip-template-id` 指向 `tooltip_templates.hbs` 里的 `<template>`                                                         |
| 按钮               | `components/action_button.hbs`（`variant` + `intent`）、`components/icon_button.hbs`；开发环境 `/devtools/buttons`、`/devtools/banners`、`/devtools/inputs` 展示所有变体                                                                                |
| 横幅               | `banners.ts` + `components/banner.hbs`；输入框上方的横幅用 `compose_banner.ts`                                                                                                                                                                          |
| 下拉选择           | `dropdown_widget.ts` 的 `DropdownWidget`                                                                                                                                                                                                                |
| 药丸输入（选人等） | `input_pill.create({$container, create_item_from_text, get_text_from_item, get_display_value_from_item})`，现成的有 `user_pill.ts`、`stream_pill.ts`、`user_group_pill.ts` 等；补全用 `pill_typeahead.ts`；`onPillCreate`/`onPillRemove` 里更新保存状态 |
| 长列表、可排序表格 | `list_widget.create($container, items, {name, get_item, modifier_html, filter, $simplebar_container})`，滚动时渐进渲染                                                                                                                                  |
| 自动补全           | `bootstrap_typeahead.ts`、`typeahead_helper.ts`                                                                                                                                                                                                         |
| 标签切换           | `components.toggle(...)`                                                                                                                                                                                                                                |
| 加载中、保存反馈   | `loading.make_indicator`、`loading.show_button_spinner`；设置项用 `settings_ui.do_settings_change`；短暂提示 `feedback_widget.show`                                                                                                                     |
| 日期时间选择       | `flatpickr.ts`                                                                                                                                                                                                                                          |
| 权限判断           | `settings_data.ts` 的 `user_can_*`、`user_has_permission_for_group_setting`，不在界面代码里重写权限逻辑                                                                                                                                                 |

药丸容器的 HTML：`<div class="pill-container"><div class="input" contenteditable="true"></div></div>`，
药丸会插在 `.input` 之前。

## 图标

- 写法：`<i class="zulip-icon zulip-icon-<name>" aria-hidden="true"></i>`，对应 `web/icons/<name>.svg`
  （由 `web/icons/zulip-icons.font.cjs` 和 `template.hbs` 生成字体）。新界面一律用 `zulip-icon`。
- 先在 `web/icons/` 里找现成的。需要新图标时优先选 Lucide 风格，SVG 要整理成：只有 `<svg>`
  （`xmlns`、`width`、`height`、`viewBox`）和只带 `d` 属性的 `<path>`；不能有 `fill`、`fill-rule`、
  `stroke`（lint 检查）。
- 转字体后变形的两种情况：描边图标要在 Inkscape 里 Path → Stroke to Path，再把描边设为 0；
  带 `evenodd` 镂空的要依次 Object to Path → Flatten → Combine。
- 第三方来源的图标，把来源告诉总领登记署名。
- 装饰性图标（旁边有文字）加 `aria-hidden="true"`；只有图标的按钮要有提示气泡，并加文案相同的 `aria-label`。

## CSS

- **颜色**写成变量，放在 `web/styles/app_variables.css` 的 `:root`，用 `light-dark(浅色值, 深色值)`
  一次给出两套主题；组件 CSS 里只用 `var(--color-...)`。调色板变量（`--grey-*`、`--purple-*` 等）在同一文件。
- `light-dark()` 表达不了的深色覆盖写进 `web/styles/dark_theme.css` 的 `%dark-theme { ... }`
  （它被扩展到 `:root.dark-theme` 和跟随系统时的 `:root.color-scheme-automatic`）。
  JS 里判断主题用 `settings_data.using_dark_theme()`。
- 颜色只用 `hsl()`：stylelint 禁止十六进制、`rgb()` 和颜色名。边框宽度不用 `thin`/`medium`/`thick`。
- 基础字号和行高是用户设置（`--base-font-size-px`、`--base-line-height-unitless`，由
  `information_density.ts` 设置），所以尺寸用 `em`，惯例在注释里写换算：`0.1875em; /* 3px at 16px/1em */`。
- 断点用变量：媒体查询 `@media (width < $xl_min)`，容器查询 `@container app (width < $cq_md_min)`，
  定义在 `web/src/css_variables.ts`。支持 CSS 嵌套。
- 类名用 kebab-case，唯一、便于 `git grep`；选择器不带标签名。

## TypeScript

- 新模块用 TypeScript；上面三个 `.js` 文件原样编辑。import 路径带 `.ts` 扩展名。
- `tsconfig.json` 开了 `strict`、`noUncheckedIndexedAccess`、`exactOptionalPropertyTypes`：
  数组和对象下标取值可能是 `undefined`；可选属性不能直接赋 `undefined`，除非类型里写了。
- 服务端数据用 zod 校验，只能 `import * as z from "zod/mini"`（直接导入 `zod` 会被 eslint 拦下）。
  mini 是函数式写法：`z.optional(z.string())`、`z.nullable(...)`、`z.array(...)`，没有 `.optional()` 链式调用；
  类型用 `z.infer<typeof schema>`。
- 断言用 `minimalistic-assert` 的 `assert`；错误上报用 `blueslip.error`/`blueslip.warn`。
- eslint 禁止循环 import（`import-x/no-cycle`）：两个模块互相需要时，把共用部分抽到新模块，
  或通过 `initialize({...})` 传入回调。
- 其他常见 lint：不用 `for...in` 遍历数组；用 `+= 1` 代替 `++`；不用 `alert`；
  jQuery 选择器不用 `:visible`、`:first` 这类伪类。单独做类型检查：`./tools/run-tsc`。

## URL 与导航

- 相关模块：`hashchange.ts`、`hash_parser.ts`、`hash_util.ts`、`browser_history.ts`。
- 代码已经自己更新了界面、只需改 URL：`browser_history.update(hash)`；要让 hashchange 去渲染目标页面：
  `browser_history.go_to_location(hash)`。
- 新的覆盖层路由：加进 `hash_parser.is_overlay_hash` 的列表，并在 `hashchange` 的 `do_hashchange_overlay`
  加分支；普通视图在 `do_hashchange_normal`。
- 改了导航逻辑要手测：站内链接、浏览器后退、覆盖层内切换（不应重播打开动画）、刷新后回到原处、
  服务端触发的重载（`reload.ts` 把状态存进 `#reload` 哈希，`reload_setup.ts` 恢复）。

## 无障碍与键盘

- 所有操作都能用键盘完成；全局快捷键在 `hotkey.ts`，菜单内导航用 `popover_menus.popover_items_handle_keyboard`。
- 图片有 `alt`；ARIA 属性用对；文字对比度达到 WCAG AA。

## 其他子系统速查

| 子系统       | 代码                                                                                                                                                                              |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 未读         | `unread.ts`：初始 `unread_msgs` 加 `message`、`update_message_flags`、`update_message` 事件维护。只在包含完整会话的视图里随阅读标记已读，搜索视图不标记                           |
| 输入状态提示 | 发送 `typing_status.ts`；接收 `typing_events.ts`、`typing_data.ts`                                                                                                                |
| 消息内小部件 | 投票、待办、zform：`widgets.ts` 注册，`widgetize.ts`、`submessage.ts`、`poll_widget.ts`、`todo_widget.ts`、`zform.ts`，模板在 `web/templates/widgets/`，数据经 `/json/submessage` |
| 斜杠命令     | `/light`、`/dark` 等：`zcommand.ts` → `/json/zcommand`；补全列表 `composebox_typeahead.ts` 的 `slash_commands`                                                                    |
| 一次性提示   | `onboarding_steps.ts`：`ONE_TIME_NOTICES_TO_DISPLAY.has(name)` 判断是否显示，显示后 `post_onboarding_step_as_read(name)`；名称由后端在 `zerver/lib/onboarding_steps.py` 注册      |
| 图片缩略图   | 消息 HTML 只含一种尺寸，`postprocess_content.ts` 按 `thumbnail.ts` 的 `preferred_format` 改写 URL                                                                                 |
| 表情         | `emoji.ts`（如 `get_emoji_details_by_name`）、`emoji_picker.ts`；数据来自 `static/generated/emoji/emoji_codes.json`                                                               |
| 常用数据     | `people.ts`、`stream_data.ts`、`sub_store.ts`、`user_groups.ts`、`message_store.ts`、`narrow_state.ts`                                                                            |

## 测试

写法见 `guides/testing.md` 的「前端：`tools/test-js-with-node`」。新组织设置更新
`web/tests/lib/example_realm.cjs`；新事件在 `web/tests/lib/events.cjs` 加示例、在
`web/tests/dispatch.test.cjs` 加测试。
