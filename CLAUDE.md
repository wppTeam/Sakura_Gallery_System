# CLAUDE.md

本项目的开发约定、架构、合规要求与 AI 渠道用法统一维护在 **[AGENTS.md](AGENTS.md)**，
请以那份为唯一来源，本文件不再重复内容以免两处不一致。

- 开发指南与约定：[AGENTS.md](AGENTS.md)
- 分期时间表与验收判据：[docs/ROADMAP.md](docs/ROADMAP.md)
- 公共端设计方向与色板实测值：[design/DIRECTION.md](design/DIRECTION.md)
- 可交互设计原型：`design/index.html`

**凭据一律不写入仓库。** 服务器地址、SSH 账号、sudo 口令、数据库与对象存储密钥
存本地未跟踪文件或密码管理器；脚本通过环境变量读取。