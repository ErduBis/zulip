# 交互设计指南

给交互设计角色。方案格式、界面检查清单见开发规范；这里是让方案贴合 Zulip 的设计惯例，以及截图验收的做法。

## 原则

- **先找现成的**：Zulip 里已有同类交互的，照着它设计，在方案「参照」里写明沿用哪个界面、哪个组件。
  确实没有合适的才设计新样式，并作为待定问题列出。
- **界面能说清的不靠文档**：一个功能需要大段说明才能用，先改流程或界面文字。
- **实时**：Zulip 的数据变化会实时推送到所有打开的页面，方案要写清别的标签页、别的用户看到什么变化。
- **少打扰**：新提示优先放在用户正在操作的位置；需要告知新功能时，用一次性提示（见下表）。

## 去哪里看现有组件

- 开发服务器上的组件样例：`http://localhost:9991/devtools/buttons/`、`/devtools/banners/`、
  `/devtools/inputs/`；其他开发工具入口在 `/devtools/`。
- 在应用里找到相似功能，用 `/screenshot-dev` 截下来作为参照附在方案目录里。
- 想知道某段界面用的是哪个组件：`git grep '界面上的英文原文' web/templates web/src`。

方案里用下表的名称指称组件，前端能直接对应到代码：

| 名称           | 用途                                                                                  | 代码                                                                                                               |
| -------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| 按钮           | 样式 solid / subtle / text × 意图 brand / neutral / info / success / warning / danger | `web/templates/components/action_button.hbs`，纯图标按钮 `icon_button.hbs`                                         |
| 横幅（banner） | 页内提示，意图同上，可带按钮和关闭                                                    | `web/templates/components/banner.hbs`；输入框上方 `web/src/compose_banner.ts`；页面顶部 `web/src/navbar_alerts.ts` |
| 对话框         | 标题 + 内容 + 提交/取消；默认按钮 “Save changes” / “Cancel”                           | `web/src/dialog_widget.ts`                                                                                         |
| 确认框         | 二次确认，默认按钮 “Confirm”；危险操作用 danger 样式                                  | `web/src/confirm_dialog.ts`（`dangerous_action`）                                                                  |
| 弹出菜单       | 点图标弹出的操作菜单                                                                  | `web/src/popover_menus.ts`                                                                                         |
| 提示气泡       | 悬停说明、快捷键提示                                                                  | `web/src/tippyjs.ts`、`web/templates/tooltip_templates.hbs`                                                        |
| 下拉选择       | 可搜索的单选列表                                                                      | `web/src/dropdown_widget.ts`                                                                                       |
| 切换标签       | 同一区域内切换视图                                                                    | `web/src/components.ts`                                                                                            |
| 输入胶囊       | 输入并选择多个用户、频道、用户组                                                      | `web/src/input_pill.ts`，配合输入联想 `web/src/typeahead_helper.ts`                                                |
| 列表/表格      | 带搜索、排序的长列表；空状态                                                          | `web/src/list_widget.ts`、`web/templates/empty_list_widget_for_list.hbs`、`..._for_table.hbs`                      |
| 撤销提示       | 操作后短暂显示、可撤销（如 “Undo mute”）                                              | `web/src/feedback_widget.ts`                                                                                       |
| 结果提示       | 就地显示 “Saved”、失败原因                                                            | `web/src/ui_report.ts`                                                                                             |
| 一次性提示     | 新功能介绍，用户看过后不再出现（横幅、弹窗、气泡）                                    | `zerver/lib/onboarding_steps.py` 的 `ONE_TIME_NOTICES`，`web/src/onboarding_steps.ts`                              |

图标：现有图标在 `web/icons/`（文件名即图标名，类名 `zulip-icon-<文件名>`）；没有合适的，从
Lucide（lucide.dev）里选，在方案里写图标名。

## 设置页的惯例

- **个人设置**：改完立即保存，旁边显示 “Saving” / “Saved”（`web/src/settings_ui.ts`）。
- **组织设置**：每个小节有改动时出现 “Save changes” / “Discard” 按钮
  （`web/templates/settings/settings_save_discard_widget.hbs`）。
- **没有权限的用户**：控件显示为禁用，悬停提示说明原因，如 “Only organization administrators can edit
  this setting.”。方案里写出这句提示的文案。

## 界面文字

- **句首大写（sentence case）**：只有第一个词和专有名词首字母大写，“Channel settings” 而不是
  “Channel Settings”；缩写按标准写法：URL、API、ID。`./tools/check-capitalization` 会检查所有标记翻译的字符串，
  例外列表是 `tools/lib/capitalization.py` 的 `IGNORED_PHRASES`（视图名 “Inbox”、“Recent conversations”
  在句中也大写）。
- **用词**：channel、topic、direct message（DM）、organization、user group、bot。“realm” 不能出现在界面上
  （检查脚本会报错）。中文对应词见 `custom/zh/guides/translation.md` 的术语表。
- **完整的句子**：一句话作为一条文案，句末标点包含在文案里；带变量的句子写成 “Deactivate {name}?”
  这样的整句，不拆成几段拼接。
- **数量**：能用“图标 + 数字”表达的就不用带复数的句子；必须用时按 “{count, plural, one {# message} other
  {# messages}}” 的格式写英文。
- **按钮**：用动词说明结果（“Save changes”、“Archive channel”），确认框的提交按钮写出具体动作；
  不可撤销的操作用 danger 样式并在文案里说明后果。
- **语气**：对用户称 “you”；不用 “we” 指代 Zulip。
- **长度**：中文通常比英文短，俄语、德语等更长；布局要容得下文字长度变化，不能按英文宽度写死。

## 主题、字号和宽度

- **主题**：用户可选浅色、深色、跟随系统。颜色都是成对定义的，在 `web/styles/app_variables.css`
  （`light-dark(浅色值, 深色值)`）。方案里指定颜色时，写“与某现有元素相同”或变量名；新颜色要同时给出深色值。
- **信息密度**：用户可调字号（默认 16px，紧凑 14px）和行高，布局要随字号缩放，两档都要看。
- **宽度**：窗口约 1200px 以下右侧栏收起，约 768px 以下左侧栏也收起（按字号缩放）；断点定义在
  `web/src/css_variables.ts`。另有「全宽布局」设置。
- **时间**：显示时间时跟随用户的 12/24 小时制设置。
- **动画**：系统开启“减少动态效果”时动画会被关掉，信息不能只靠动画表达。

## 键盘与无障碍

- 所有操作都能只用键盘完成：Tab 顺序与视觉顺序一致；Enter 提交或触发；Esc 关闭对话框和弹出菜单，
  关闭后焦点回到触发它的元素。方案的「适配」一节写出这些。
- **快捷键**：现有列表在 `web/templates/keyboard_shortcuts.hbs`（应用里按 `?` 打开），处理逻辑在
  `web/src/hotkey.ts`。新快捷键先对照列表避免冲突；按键写非 Mac 名称（Ctrl、Enter），Mac 上会自动显示对应键
  （`web/src/common.ts` 的 `has_mac_keyboard`）。有快捷键的按钮在提示气泡里显示快捷键。
- **纯图标按钮**必须有提示气泡，读屏文字（`aria-label`）与提示文字相同；文字旁的装饰图标对读屏隐藏。
  这些提示文字写进「文案」。
- **对比度**按 WCAG AA：正文 4.5:1，大字和图标 3:1，浅色、深色主题都要满足；状态不只靠颜色区分，
  同时用图标或文字。
- 有信息的图片要有替代文字，写进「文案」。

## 方案容易漏的情况

- 消息区的不同视图：话题、频道、综合信息、私信；频道消息和私信各一次。
- 输入框的两种尺寸（正常和展开）。
- 角色：所有者、管理员、版主、成员、访客；网络公开频道还要考虑未登录用户（spectator）。
- 输入：空、不合法、超长（中英文各一次）。
- 共存：和其他横幅同时出现、消息被静音或折叠、话题被标记为已解决、内容被编辑或删除。
- 某些用户看不到的菜单项：隐藏后不能留下多余的分隔线。

## 截图验收

- **改动前截图**：写方案时就用 `/screenshot-dev` 截下现状，放在 `custom/zh/design/<feature-name>/`，
  并在方案里记下参数（`--user`、`--path`、`--width/--height`、`--lang`、`--dark`），验收时用同样的参数截改动后。
- **精确对比**：前后两张界面状态相同（同一用户、同一页面、同一滚动位置），像素尺寸相同；
  细节用 `--element` 截同一个元素。
- **覆盖所有受影响的状态**：例如新增一个下拉设置，要截设置在页面中的样子、展开的下拉、无权限时的禁用状态和提示、
  每个取值的效果。
- **留足上下文**：截图包含周围的界面，能看出新元素和相邻元素是否协调；改了公共样式的，前端给出
  `git grep` 选择器的结果，逐处截图。
- 用静态截图；交互过程用 `/visual-test` 截成一组按顺序排列的截图。
- 汇报里用表格并排对比：

  ```markdown
  | 改动前                  | 改动后                 |
  | ----------------------- | ---------------------- |
  | ![](settings-before.png) | ![](settings-after.png) |
  ```

- 默认至少截：中文和英文界面、1280 和 480 两种宽度；改了颜色的加深色主题。
