import re

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
}
W = f"{{{NS['w']}}}"

CN_NUM = "一二三四五六七八九十百零〇两"
MAIN_SECTION_RE = re.compile(rf"^第[{CN_NUM}0-9]+[条章]")
ATTACHMENT_PARENT_RE = re.compile(rf"^第[{CN_NUM}0-9]+[条章]\s*附件\s*$")
ATTACHMENT_RE = re.compile(rf"^附件\s*([{CN_NUM}0-9]+)(?:\s*$|[：:、\s])")
ATTACHMENT_LIST_ITEM_RE = re.compile(r"^\d+[.、]\s*附件")
LEVEL2_RE = re.compile(rf"^[{CN_NUM}]+、")
LEVEL3_RE = re.compile(rf"^（[{CN_NUM}]+）")
TITLE_KEYWORD_RE = re.compile(r"(细则|标准|协议|说明书|承诺书|清单|要求|任务书|方案|需求|报告|函)$")
LABEL_KEYWORD_RE = re.compile(
    r"(目的|对象|分工|内容|方式|结果|其他|要求|标准|范围|期限|责任|义务|说明|证明|来源|包装|请假|考核|罚则|承诺|服务|电话)"
)
PLAIN_LABEL_RE = re.compile(r"^[\u4e00-\u9fa5A-Za-z0-9（）()]{2,24}[。；;：:]$")
TAIL_MARKER_RE = re.compile(r"(以下无正文|以下为合同签署栏|签署|签字|盖章|法定代表人|授权代表)")

NODE_TARGET_TOKENS = 700
NODE_SOFT_LIMIT_TOKENS = 1000
NODE_HARD_LIMIT_TOKENS = 1800
SUMMARY_TRIGGER_MIN_TOKENS = 300
SUMMARY_MAX_CHARS = 180
STRUCTURE_INLINE_BUDGET_TOKENS = 6000
STRUCTURE_PAGED_BUDGET_TOKENS = 20000
