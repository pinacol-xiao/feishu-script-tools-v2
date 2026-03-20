import streamlit as st
import requests
import json
import re
import time

# ================= 配置区域 =================
# 🔴 飞书后台最新的 App ID 和 Secret
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]

API_HOST = "https://open.feishu.cn/open-apis"
# ===========================================

# 网页图标配置
st.set_page_config(page_title="剧本拼接工具", page_icon="📄", layout="centered")

class FeishuDriveUploader:
    def __init__(self, app_id, app_secret):
        self.app_id = app_id
        self.app_secret = app_secret
        self.token = ""

    def get_tenant_access_token(self):
        url = f"{API_HOST}/auth/v3/tenant_access_token/internal"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        res = requests.post(url, headers=headers, json={"app_id": self.app_id, "app_secret": self.app_secret})
        self.token = res.json().get("tenant_access_token")

    def upload_txt_file(self, file_name, text_content):
        if not self.token: self.get_tenant_access_token()
        url = f"{API_HOST}/drive/v1/files/upload_all"
        headers = {"Authorization": f"Bearer {self.token}"}
        content_bytes = text_content.encode('utf-8')
        
        files = {
            'file_name': (None, file_name),
            'parent_type': (None, 'explorer'), 
            'parent_node': (None, ''),
            'size': (None, str(len(content_bytes))),
            'file': (file_name, content_bytes, 'text/plain')
        }
        
        res = requests.post(url, headers=headers, files=files).json()
        if res.get("code") != 0:
            raise Exception(f"飞书返回错误: {res}")
            
        file_token = res["data"]["file_token"]
        file_url = f"https://www.feishu.cn/file/{file_token}"
        return file_token, file_url

    def add_user_permission(self, file_token, email):
        url = f"{API_HOST}/drive/v1/permissions/{file_token}/members?type=file"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        payload = {"member_type": "email", "member_id": email, "perm": "full_access"}
        requests.post(url, headers=headers, json=payload)

def get_sort_weight(filename):
    if "主题" in filename: return 1
    if "主角小传" in filename: return 2
    if "反派小传" in filename or "对手" in filename: return 3
    if "配角小传" in filename: return 4
    if "三幕大纲" in filename or "核心剧情事件" in filename: return 5
    if "细纲" in filename: return 6
    if "shootingscript" in filename.lower():
        match = re.search(r'第(\d+)集', filename)
        ep = int(match.group(1)) if match else 99
        return 100 + ep 
    return 999

# ================= 网页 UI 与核心逻辑 =================
st.title("剧本拼接工具")
st.markdown("将分散的剧本文件自动拼接为**剧本文档**与**规模化交付文档**，并一键导入飞书。")
st.caption("创作者：@pinacol_xiao")

if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# 👇 变更点：把第一步的标题独立出来，和第二步保持格式绝对统一
st.markdown("**第一步：上传所有 TXT 剧本文件**")

uploaded_files = st.file_uploader(
    "上传文件", # 这个辅助标签虽然存在，但会被下一行代码隐藏
    accept_multiple_files=True, 
    type=['txt'], 
    key=f"uploader_{st.session_state.uploader_key}",
    label_visibility="collapsed" # 核心魔法：隐藏原生标签
)

if uploaded_files:
    if st.button("🗑️ 一键清空已上传文件"):
        st.session_state.uploader_key += 1 
        st.rerun() 

default_script_name = ""
default_date = time.strftime("%y%m%d") 

if uploaded_files:
    first_file_name = uploaded_files[0].name
    clean_name = re.sub(r'[【】\[\]]', '', first_file_name)
    match = re.search(r'^(.*?)_(\d{4,6})_', clean_name)
    
    if match:
        default_script_name = match.group(1).strip() 
        default_date = match.group(2) 
    else:
        default_script_name = clean_name.split('_')[0].replace(".txt", "").strip()

saved_name = st.query_params.get("name", "")

if "email_input" not in st.session_state:
    st.session_state.email_input = st.query_params.get("email", "")

def format_email_callback():
    val = st.session_state.email_input.strip()
    if val and "@" not in val:
        st.session_state.email_input = val + "@bytedance.com"
    st.query_params["email"] = st.session_state.email_input

# 这里的标题现在和上面的第一步完全对称了！
st.markdown("**第二步：确认信息** (剧名与日期已自动提取)")
st.info("💡 **提示：** 输入名字和邮箱后，将本页面网址加入书签，即可记忆个人专属信息")

with st.container():
    col1, col2 = st.columns(2)
    with col1:
        script_name = st.text_input("剧名", value=default_script_name)
        user_name = st.text_input("你的名字", value=saved_name)
        if user_name != saved_name:
            st.query_params["name"] = user_name
            
    with col2:
        script_date = st.text_input("日期", value=default_date)
        st.text_input(
            "飞书邮箱 (输入前缀后按回车自动补齐)", 
            key="email_input",
            on_change=format_email_callback,
            placeholder="如: luhua.101"
        )

user_email = st.session_state.email_input

doc_title = f"{script_name}_{user_name}_{script_date}"
download_container = st.empty()

if st.button("**🚀 第三步：开始拼接并上传飞书**", use_container_width=True, type="primary"):
    if not uploaded_files:
        st.warning("请先上传 TXT 文件！")
    elif not user_email or not user_name:
        st.warning("请填写你的名字和接收人的飞书邮箱！")
    else:
        is_30_eps = any("核心剧情事件" in f.name for f in uploaded_files)
        
        sorted_files = sorted(uploaded_files, key=lambda f: get_sort_weight(f.name))
        merged_text = "# 1. 原创意\n\n## 1.1 创意内容\n\n## 1.2 来源\n\n---\n\n"
        
        extracted_sanmu = ""
        extracted_xigang = ""
        extracted_shooting = ""
        state_shooting_printed = False 
        
        skip_keywords = [
            "质检结果", "通过质检", "经逐一审核", "综合评估", "推荐:", "推荐：", 
            "推荐理由", "质检分析", "修改内容", "问题清单", "修正说明", "发现问题", 
            "结构说明", "方案 1", "方案 2", "方案 3", "方案1", "方案2", "质检理由", 
            "位置 |", "问题描述", "问题类型", "The following table:",
            "质检说明：", "检查结论：", "修改后的完整分集细纲：" 
        ]
        
        resume_keywords = ["核心事件ID", "Theme", "情绪:", "情绪：", "适用冲突", "主角:", "主角：", "对手:", "对手：", "Act ", "姓名", "分场信息", "Shooting script", "Shooting Script", "人物关系图谱", "角色关系图"]

        with st.spinner('正在进行数据清洗与双文档拼接...'):
            for file in sorted_files:
                filename = file.name
                raw_lines = file.getvalue().decode("utf-8").splitlines()
                
                if "主题" in filename: merged_text += "# 2. 主题\n\n"
                elif "主角小传" in filename: merged_text += "# 3. 主角小传\n\n"
                elif "反派小传" in filename or "对手" in filename: merged_text += "# 4. 对手小传\n\n"
                elif "配角小传" in filename: merged_text += "# 5. 配角小传\n\n"
                elif "三幕大纲" in filename: merged_text += "# 6. 三幕表格大纲\n\n"
                elif "核心剧情事件" in filename: merged_text += "# 6. 核心剧情事件\n\n"
                elif "细纲" in filename: merged_text += "# 7. 单集细纲\n\n"
                elif "shootingscript" in filename.lower():
                    if not state_shooting_printed:
                        merged_text += "# 8. Shooting script\n\n"
                        state_shooting_printed = True
                    match = re.search(r'第(\d+)集', filename)
                    ep_num = match.group(1) if match else "X"
                    merged_text += f"#### EP{ep_num}\n\n"
                else:
                    merged_text += f"# {filename}\n\n"

                lines = []
                skip_mode = False
                for line in raw_lines:
                    raw_str = line.strip()
                    clean_str = re.sub(r'^[*#\-\s\|]+', '', raw_str) 
                    
                    if '★' in clean_str or '✓' in clean_str:
                        skip_mode = True
                        continue
                    if re.match(r'^\d+\.\s*(.*?契合度|.*?符合度|淘汰.*?原因|.*?检查|.*?错误|角色.*?问题|集与集衔接断裂)[：:]?', clean_str):
                        skip_mode = True
                        continue
                    if any(clean_str.startswith(kw) for kw in skip_keywords):
                        skip_mode = True
                        continue
                    if re.match(r'^第\d+集([：:]|\s*\[)\s*(将|在|字数|添加)', clean_str):
                        skip_mode = True
                        continue
                    if skip_mode and re.match(r'^第\d+集\s*\|', clean_str):
                        continue
                    if re.match(r'^(《.*?》)?(三幕大纲|分集细纲|表格大纲|Shooting script).*?[\(（]修正版[\)）]', clean_str):
                        skip_mode = True
                        continue
                        
                    is_resume = False
                    if any(clean_str.startswith(kw) for kw in resume_keywords): is_resume = True
                    if clean_str.startswith("集数 |") or clean_str.startswith("Episode |") or clean_str.startswith("编号/ID |"): is_resume = True
                    if re.match(r'^第\d+集([：:]|\s*\[)', clean_str) and not re.match(r'^第\d+集([：:]|\s*\[)\s*(将|在|字数|添加)', clean_str): is_resume = True
                    if re.match(r'^1\.\s+[A-Za-z\u4e00-\u9fa5]', clean_str): is_resume = True

                    if is_resume: skip_mode = False
                    if not skip_mode: lines.append(line)
                
                cleaned_file_text = "\n".join(lines)
                merged_text += cleaned_file_text + "\n\n---\n\n"
                
                if "三幕大纲" in filename:
                    modified_sanmu = re.sub(r'^#*\s*(Act\s*\d+.*)', r'#### \1', cleaned_file_text, flags=re.IGNORECASE|re.MULTILINE)
                    extracted_sanmu += modified_sanmu + "\n\n"
                elif "细纲" in filename:
                    extracted_xigang += cleaned_file_text + "\n\n"
                elif "shootingscript" in filename.lower():
                    match = re.search(r'第(\d+)集', filename)
                    ep_num = match.group(1) if match else "X"
                    extracted_shooting += f"#### EP{ep_num}\n\n{cleaned_file_text}\n\n"
        
        doc2_title = f"TT<> 规模化合作沟通文档_{script_name}"
        
        if is_30_eps:
            script_section = f"### 单集细纲\n\n{extracted_xigang}\n\n### Shooting Script\n\n{extracted_shooting}"
        else:
            script_section = f"### 三幕大纲\n\n{extracted_sanmu}\n\n### Shooting Script\n\n{extracted_shooting}"
        
        doc2_text = f"""# 1. 题材和设定
## 1.1 剧本

{script_section}

## 1.2 人物形象参考
| 角色 | | | |
| :--- | :--- | :--- | :--- |
| 男主 | | | |
| 女主 | | | |

# 2. 第一集demo验收(只修改第一集,第一集验收成功后,后续剧集批量制作)
## Version 1
视频粘贴:【】
反馈
| 分镜截图 | 视频时点(大致) | 反馈 |
| :--- | :--- | :--- |
| | | |
| | | |
| | | |
| | | |
| | | |
| | | |
| | | |

# 3. 成片交付
## 3.1 剧名
* 剧集名字：
* 一句话剧集简介：
* hashtags (3个)：
* target用户：

## 3.2 3:4封面

## 3.3 分集视频【只上传视频附件】
### EP1
### EP2
### EP3
### EP4
### EP5
### EP6
### EP7
### EP8
### EP9
### EP10

## 3.4 视频反馈
| 集数 | 分镜截图 | 视频时点(大致) | TT反馈 | 供应商备注 |
| :--- | :--- | :--- | :--- | :--- |
| | | | | |

## 3.5 四国语言【英语/葡语/日语/印尼语】字幕视频压缩包(单个压缩包 <2G)
英语

葡语

日语

印尼语
"""
        
        st.success("文件清洗与双通道拼接完成 ✅") 

        file_name_1_with_ext = f"{doc_title}.txt"
        file_name_2_with_ext = f"{doc2_title}.txt"
        
        with download_container:
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.download_button(
                    label="保存【剧本汇总文档】⬇️",
                    data=merged_text.encode("utf-8"),
                    file_name=file_name_1_with_ext,
                    mime="text/plain",
                    type="secondary"
                )
            with col_d2:
                st.download_button(
                    label="保存【规模化沟通文档】⬇️",
                    data=doc2_text.encode("utf-8"),
                    file_name=file_name_2_with_ext,
                    mime="text/plain",
                    type="secondary"
                )

        try:
            with st.spinner('正在将两份文档同步传输至飞书云盘...'):
                uploader = FeishuDriveUploader(APP_ID, APP_SECRET)
                
                token1, url1 = uploader.upload_txt_file(file_name_1_with_ext, merged_text)
                uploader.add_user_permission(token1, user_email)
                
                token2, url2 = uploader.upload_txt_file(file_name_2_with_ext, doc2_text)
                uploader.add_user_permission(token2, user_email)
                
            st.markdown("---")
            st.markdown("### 飞书直传成功！🎉")
            
            st.markdown(f"""
            - 📄 **文档一：** [{doc_title}]({url1})
            - 📁 **文档二：** [{doc2_title}]({url2})
            
            *(打开上方链接后，点击页面顶部的「转为在线文档」 按钮即可)*
            """)

        except Exception as e:
            st.error(f"上传飞书云盘时出错，请检查 App 权限。报错信息: {e}")