import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from config import DB_FILE

class Database:
    def __init__(self):
        self.db_file = DB_FILE
        self.data = self._load_data()

    def _load_data(self) -> dict:
        if os.path.exists(self.db_file):
            with open(self.db_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "users": {},
            "banned_users": [],
            "premium_users": [],
            "groups": {},  
            "statistics": {
                "total_messages": 0,
                "total_images": 0,
                "daily_messages": {},
            }
        }

    def _save_data(self):
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add_user(self, user_id: int, username: str, first_name: str):
        if str(user_id) not in self.data["users"]:
            self.data["users"][str(user_id)] = {
                "username": username,
                "first_name": first_name,
                "join_date": datetime.now().isoformat(),
                "message_count": 0,
                "image_count": 0,
                "daily_image_count": {},
                "last_active": datetime.now().isoformat()
            }
            self._save_data()

    def update_user_activity(self, user_id: int, message_type: str = "text"):
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Update user statistics
        if str(user_id) in self.data["users"]:
            user = self.data["users"][str(user_id)]
            if message_type == "text":
                user["message_count"] += 1
                self.data["statistics"]["total_messages"] += 1
            elif message_type in ["photo", "image"]:
                user["image_count"] += 1
                self.data["statistics"]["total_images"] += 1
                
                # Update daily image count
                if "daily_image_count" not in user:
                    user["daily_image_count"] = {}
                if today not in user["daily_image_count"]:
                    user["daily_image_count"] = {today: 0}
                user["daily_image_count"][today] = user["daily_image_count"].get(today, 0) + 1
                
            user["last_active"] = datetime.now().isoformat()
            self._save_data()

    def get_user_stats(self, user_id: int) -> Optional[dict]:
        return self.data["users"].get(str(user_id))

    def get_all_users(self) -> List[dict]:
        return list(self.data["users"].values())

    def get_total_users(self) -> int:
        return len(self.data["users"])

    def get_daily_stats(self) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.data["statistics"]["daily_messages"].get(today, {"messages": 0, "images": 0})

    def get_total_stats(self) -> dict:
        return {
            "total_messages": self.data["statistics"]["total_messages"],
            "total_images": self.data["statistics"]["total_images"],
            "total_users": len(self.data["users"])
        }

    def get_daily_image_count(self, user_id: int) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        user = self.data["users"].get(str(user_id), {})
        return user.get("daily_image_count", {}).get(today, 0)

    def ban_user(self, user_id: int):
        if str(user_id) not in self.data["banned_users"]:
            self.data["banned_users"].append(str(user_id))
            self._save_data()

    def unban_user(self, user_id: int):
        if str(user_id) in self.data["banned_users"]:
            self.data["banned_users"].remove(str(user_id))
            self._save_data()

    def get_banned_users(self) -> list:
        """Get list of banned user IDs."""
        return self.data["banned_users"]

    def get_user_info(self, user_id: int) -> dict:
        """Get user information by ID."""
        return self.data["users"].get(str(user_id))

    def is_user_banned(self, user_id: int) -> bool:
        """Check if user is banned."""
        return str(user_id) in self.data["banned_users"]

    def is_user_premium(self, user_id: int) -> bool:
        """Check if user is premium."""
        return str(user_id) in self.data.get("premium_users", [])

    def add_premium_user(self, user_id: int) -> bool:
        """Add user to premium users list. Returns True if user was added, False if already premium."""
        if "premium_users" not in self.data:
            self.data["premium_users"] = []
        if str(user_id) not in self.data["premium_users"]:
            self.data["premium_users"].append(str(user_id))
            self._save_data()
            return True
        return False

    def remove_premium_user(self, user_id: int) -> bool:
        """Remove user from premium users list. Returns True if user was removed, False if not premium."""
        if "premium_users" in self.data and str(user_id) in self.data["premium_users"]:
            self.data["premium_users"].remove(str(user_id))
            self._save_data()
            return True
        return False

    def get_premium_users(self) -> List[str]:
        return self.data.get("premium_users", [])

    def broadcast_message(self, message: str) -> List[str]:
        return list(self.data["users"].keys())

    def can_send_image(self, user_id: int) -> bool:
        """Check if user can send more images today."""
        # Ensure premium_users exists in data
        if "premium_users" not in self.data:
            self.data["premium_users"] = []
            self._save_data()
            
        # Check if user is premium
        if str(user_id) in self.data["premium_users"]:
            return True  # Premium users have unlimited images
            
        today = datetime.now().strftime("%Y-%m-%d")
        user = self.data["users"].get(str(user_id))
        if not user:
            return False
            
        # Ensure daily_image_count exists for user
        if "daily_image_count" not in user:
            user["daily_image_count"] = {}
            
        # Get today's count, default to 0 if not exists
        daily_count = user["daily_image_count"].get(today, 0)
        return daily_count < 5  # Regular users limited to 5 images per day

    def increment_daily_image_count(self, user_id: int):
        """Increment the user's daily image count."""
        today = datetime.now().strftime("%Y-%m-%d")
        user = self.data["users"].get(str(user_id))
        if user:
            # Ensure daily_image_count exists
            if "daily_image_count" not in user:
                user["daily_image_count"] = {}
                
            # Reset count if it's a new day
            if today not in user["daily_image_count"]:
                user["daily_image_count"][today] = 0
                
            # Increment count
            user["daily_image_count"][today] += 1
            
            # Update image count in user stats
            user["image_count"] = user.get("image_count", 0) + 1
            
            # Save changes
            self._save_data()

    def add_group(self, chat_id: int, title: str):
        """إضافة مجموعة جديدة أو تحديث معلوماتها"""
        if str(chat_id) not in self.data.get("groups", {}):
            self.data.setdefault("groups", {})[str(chat_id)] = {
                "title": title,
                "join_date": datetime.now().isoformat(),
                "message_count": 0,
                "last_active": datetime.now().isoformat()
            }
        else:
            # تحديث اسم المجموعة إذا تغير
            self.data["groups"][str(chat_id)]["title"] = title
            self.data["groups"][str(chat_id)]["last_active"] = datetime.now().isoformat()
        self._save_data()

    def get_all_groups(self) -> List[Dict]:
        """الحصول على قائمة جميع المجموعات"""
        groups = []
        for chat_id, group_data in self.data.get("groups", {}).items():
            groups.append({
                "chat_id": chat_id,
                "title": group_data["title"],
                "join_date": group_data["join_date"],
                "message_count": group_data["message_count"],
                "last_active": group_data["last_active"]
            })
        return groups

    def update_group_activity(self, chat_id: int):
        """تحديث نشاط المجموعة"""
        if str(chat_id) in self.data.get("groups", {}):
            self.data["groups"][str(chat_id)]["message_count"] += 1
            self.data["groups"][str(chat_id)]["last_active"] = datetime.now().isoformat()
            self._save_data()

    def update_group_info(self, chat_id: str, info: dict) -> None:
        """تحديث معلومات المجموعة."""
        if 'groups' not in self.data:
            self.data['groups'] = {}
        
        if str(chat_id) in self.data['groups']:
            self.data['groups'][str(chat_id)].update(info)
            self._save_data()

    def remove_group(self, chat_id: str) -> None:
        """حذف مجموعة من قاعدة البيانات."""
        if 'groups' in self.data and str(chat_id) in self.data['groups']:
            del self.data['groups'][str(chat_id)]
            self._save_data()

    def search_groups(self, query: str) -> list:
        """البحث عن مجموعات باسمها أو معرفها."""
        if 'groups' not in self.data:
            return []
        
        results = []
        query = query.lower()
        
        for chat_id, group in self.data['groups'].items():
            if (query in str(chat_id).lower() or 
                query in group.get('title', '').lower()):
                results.append(group)
        
        return results

    def cleanup_inactive_groups(self) -> tuple:
        """حذف المجموعات غير النشطة وإرجاع عدد المجموعات المحذوفة."""
        if 'groups' not in self.data:
            return 0, []
        
        inactive_groups = []
        removed_count = 0
        
        for chat_id, group in list(self.data['groups'].items()):
            if group.get('message_count', 0) == 0:
                inactive_groups.append(group)
                del self.data['groups'][chat_id]
                removed_count += 1
        
        if removed_count > 0:
            self._save_data()
        
        return removed_count, inactive_groups
