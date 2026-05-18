# Jellyfin STRM 迁移项目背景与实施说明

## 项目背景

当前本地 Jellyfin 媒体库已从：

```text id="a1m4v8"
本地 MP4 文件
```

迁移为：

```text id="b5q2k7"
STRM 远程播放模式
```

即：

原媒体文件：

```text id="c8v1m3"
ABP-123.mp4
```

被替换为：

```text id="d2k9q5"
ABP-123.strm
```

STRM 文件内部仅保存：

```text id="e7m3v1"
媒体播放入口 URL
```

例如：

```text id="f4q8k2"
https://cms.example.com/play/abp-123
```

实际视频文件已迁移至：

* [115网盘](https://115.com?utm_source=chatgpt.com)
* 或其它云盘系统

播放时：

```text id="g9v1m6"
Jellyfin
↓
STRM
↓
CMS
↓
动态解析真实播放链接
↓
云盘视频
```

从而实现：

* 本地零视频存储
* 云媒体库
* 按需取流
* 大容量低成本媒体系统

---

# 当前问题

由于 Jellyfin 的媒体识别机制：

```text id="h3k7q4"
基于 ItemId
而不是番号
```

当：

```text id="i6m2v9"
mp4 → strm
```

发生后：

Jellyfin 会认为：

```text id="j1q8k5"
旧媒体已删除
+
新媒体已新增
```

因此：

* 原 ItemId 失效
* 新媒体生成新的 ItemId
* UserData 关联断裂

导致：

* 收藏丢失
* 已观看状态丢失
* 播放进度丢失
* 继续观看丢失
* 播放历史失联

---

# 问题本质

并非 UserData 数据被删除。

而是：

```text id="k5v3m7"
UserData.ItemId
↓
指向旧 mp4 ItemId
```

而新的 STRM 媒体：

```text id="l8k1q2"
拥有新的 ItemId
```

导致用户状态数据无法关联。

---

# 数据库结构分析

## 主媒体表

```text id="m4q9v6"
BaseItems
```

关键字段：

| 字段        | 说明               |
| --------- | ---------------- |
| Id        | Jellyfin 媒体唯一 ID |
| Path      | 文件路径             |
| Name      | 媒体名称             |
| Type      | 媒体类型             |
| MediaType | Video 等          |

---

## 用户状态表

```text id="n7m2k5"
UserData
```

关键字段：

| 字段                    | 说明      |
| --------------------- | ------- |
| ItemId                | 关联媒体 ID |
| UserId                | 用户 ID   |
| IsFavorite            | 是否收藏    |
| Played                | 是否已观看   |
| PlayCount             | 播放次数    |
| PlaybackPositionTicks | 播放进度    |
| LastPlayedDate        | 最后播放时间  |

---

# 解决方案核心思想

# 不再依赖 Jellyfin ItemId

而是：

# 基于番号进行媒体身份恢复

例如：

```text id="o1v8q4"
ABP-123
```

作为：

```text id="p6k3m9"
逻辑媒体ID
```

因为：

* mp4 会变化
* strm 会变化
* 云盘会变化
* Jellyfin ItemId 会变化

但：

```text id="q2m7v5"
番号永远不变
```

---

# 实施方案

## 总体流程

```text id="r9k1q6"
旧数据库 old.db
↓
提取番号与 UserData
↓
新数据库 new.db
↓
提取番号与新 ItemId
↓
按番号建立映射
↓
重写 UserData.ItemId
↓
写入新库
```

---

# 具体实施步骤

---

# Step 1：停止 Jellyfin

防止 SQLite 被占用。

```bash id="s4m8v2"
docker stop jellyfin
```

---

# Step 2：备份数据库

```bash id="t7q1k5"
cp library.db library.db.bak
```

---

# Step 3：读取旧数据库

从：

```text id="u3v9m1"
old.db
```

提取：

* mp4 对应番号
* UserData

SQL：

```sql id="v6k2q7"
SELECT
    b.Id,
    b.Path,
    u.*
FROM BaseItems b
JOIN UserData u ON b.Id = u.ItemId;
```

---

# Step 4：读取新数据库

从：

```text id="w1m5v8"
new.db
```

提取：

* strm 对应番号
* 新 ItemId

SQL：

```sql id="x5q8k3"
SELECT
    Id,
    Path
FROM BaseItems;
```

---

# Step 5：番号解析与标准化

从路径提取：

```text id="y8m2v4"
/media/ABP/ABP-123.strm
↓
ABP-123
```

统一规范：

* 大写
* 去除 `_`
* 去除空格
* 标准化 `-`

---

# 推荐番号正则

```regex id="z3k7q1"
([A-Z]{2,10})[-_ ]?(\d{2,6})
```

---

# Step 6：建立映射关系

生成：

```text id="a9m4v6"
番号
↓
old ItemId
↓
new ItemId
↓
UserData
```

例如：

```json id="b2q8k5"
{
  "ABP-123": {
    "old_item_id": "xxx",
    "new_item_id": "yyy",
    "favorite": true,
    "played": true,
    "position": 123456789
  }
}
```

---

# Step 7：迁移 UserData

将：

```text id="c6m1v9"
旧 UserData
```

写入：

```text id="d4k7q2"
新的 ItemId
```

---

# 推荐恢复字段

| 字段                    | 是否恢复 |
| --------------------- | ---- |
| IsFavorite            | 是    |
| Played                | 是    |
| PlayCount             | 是    |
| PlaybackPositionTicks | 是    |
| LastPlayedDate        | 是    |

---

因为：

STRM 后媒体流结构可能变化。

---

# 项目实现建议

## 推荐语言

```text id="f1q9k4"
Python
```

原因：

* sqlite3 原生支持
* 正则方便
* 数据处理效率高

---

# 最终目标

恢复：

* 收藏
* 已观看
* 继续观看
* 播放历史
* 播放次数

同时：

保持：

```text id="h9k3q6"
STRM 云媒体库架构
```

从而实现：

```text id="i4m7v1"
本地仅保存：
strm + nfo + poster + metadata
```

视频文件：

完全云端化。



### 附，数据表结构如下：

UserData表的结构如下：
---
名	类型	大小	比例	Not Null	键	默认值	排序规则	不是 null ON CONFLICT	自动递增
ItemId	TEXT			No	true						false
UserId	TEXT			No	true						false
CustomDataKey	TEXT			No	true						false
AudioStreamIndex	INTEGER			Yes	false						false
IsFavorite	INTEGER			No	false						false
LastPlayedDate	TEXT			Yes	false						false
Likes	INTEGER			Yes	false						false
PlayCount	INTEGER			No	false						false
PlaybackPositionTicks	INTEGER			No	false						false
Played	INTEGER			No	false						false
Rating	REAL			Yes	false						false
SubtitleStreamIndex	INTEGER			Yes	false						false
RetentionDate	TEXT			Yes	false						false


主表是：BaseItems   结构如下：
---
名	类型	大小	比例	Not Null	键	默认值	排序规则	不是 null ON CONFLICT	自动递增
Id	TEXT			No	true						false
Album	TEXT			Yes	false						false
AlbumArtists	TEXT			Yes	false						false
Artists	TEXT			Yes	false						false
Audio	INTEGER			Yes	false						false
ChannelId	TEXT			Yes	false						false
CleanName	TEXT			Yes	false						false
CommunityRating	REAL			Yes	false						false
CriticRating	REAL			Yes	false						false
CustomRating	TEXT			Yes	false						false
Data	TEXT			Yes	false						false
DateCreated	TEXT			Yes	false						false
DateLastMediaAdded	TEXT			Yes	false						false
DateLastRefreshed	TEXT			Yes	false						false
DateLastSaved	TEXT			Yes	false						false
DateModified	TEXT			Yes	false						false
EndDate	TEXT			Yes	false						false
EpisodeTitle	TEXT			Yes	false						false
ExternalId	TEXT			Yes	false						false
ExternalSeriesId	TEXT			Yes	false						false
ExternalServiceId	TEXT			Yes	false						false
ExtraIds	TEXT			Yes	false						false
ExtraType	INTEGER			Yes	false						false
ForcedSortName	TEXT			Yes	false						false
Genres	TEXT			Yes	false						false
Height	INTEGER			Yes	false						false
IndexNumber	INTEGER			Yes	false						false
InheritedParentalRatingSubValue	INTEGER			Yes	false						false
InheritedParentalRatingValue	INTEGER			Yes	false						false
IsFolder	INTEGER			No	false						false
IsInMixedFolder	INTEGER			No	false						false
IsLocked	INTEGER			No	false						false
IsMovie	INTEGER			No	false						false
IsRepeat	INTEGER			No	false						false
IsSeries	INTEGER			No	false						false
IsVirtualItem	INTEGER			No	false						false
LUFS	REAL			Yes	false						false
MediaType	TEXT			Yes	false						false
Name	TEXT			Yes	false						false
NormalizationGain	REAL			Yes	false						false
OfficialRating	TEXT			Yes	false						false
OriginalTitle	TEXT			Yes	false						false
Overview	TEXT			Yes	false						false
OwnerId	TEXT			Yes	false						false
ParentId	TEXT			Yes	false						false
ParentIndexNumber	INTEGER			Yes	false						false
Path	TEXT			Yes	false						false
PreferredMetadataCountryCode	TEXT			Yes	false						false
PreferredMetadataLanguage	TEXT			Yes	false						false
PremiereDate	TEXT			Yes	false						false
PresentationUniqueKey	TEXT			Yes	false						false
PrimaryVersionId	TEXT			Yes	false						false
ProductionLocations	TEXT			Yes	false						false
ProductionYear	INTEGER			Yes	false						false
RunTimeTicks	INTEGER			Yes	false						false
SeasonId	TEXT			Yes	false						false
SeasonName	TEXT			Yes	false						false
SeriesId	TEXT			Yes	false						false
SeriesName	TEXT			Yes	false						false
SeriesPresentationUniqueKey	TEXT			Yes	false						false
ShowId	TEXT			Yes	false						false
Size	INTEGER			Yes	false						false
SortName	TEXT			Yes	false						false
StartDate	TEXT			Yes	false						false
Studios	TEXT			Yes	false						false
Tagline	TEXT			Yes	false						false
Tags	TEXT			Yes	false						false
TopParentId	TEXT			Yes	false						false
TotalBitrate	INTEGER			Yes	false						false
Type	TEXT			No	false						false
UnratedType	TEXT			Yes	false						false
Width	INTEGER			Yes	false						false

---
