#-*- coding: utf-8 -*-
from django.conf import settings
MENUS = [
    {'desc':u'帐号管理','per':'MP_0','menus':[
        #显示名    需要的权限   url
        (u'管理员管理', 'super', 'admin/'),
        (u'修改密码', None, 'change_password/'),
        (u'角色管理', 'role_super', 'roles/'),
        ]},
    {'desc':u'系统管理','per':'MP_2','menus':[
        (u'正式配置', 'system_setting', 'system/setting/', 'setting'),
        (u'测试配置', 'system_setting', 'system/test_setting/', 'test_setting'),
        (u'分区列表', 'zone_manage', 'zone_manage/'),
        (u'合服操作', 'merge_zone', 'merge_zone/'),
        (u'API', 'flash_api', 'flash/api/'),
        (u'JS测试', 'js_test', 'js_test/'),
        (u'更新公告', 'update_notice', 'system/setting_notice/?config_name=notice'),
        (u'分区维护', 'zone_maintain', 'maintain/'),
        ]},
    {'desc':u'APP Quản Lý','per':'MP_3','menus':[
        (u'查看用户信息', 'view_app_user', 'app_user/view_app_user/'),
        (u'查看世界信息', 'view_world', 'app_user/view_world/'),
        (u'查看世界年报', 'view_world', 'app_user/view_world_report/'),
        (u'查看跨服战场', 'view_duplicate', 'app_user/view_duplicate/'),
        (u'查看战斗记录', 'view_duplicate', 'app_user/get_fight_logs/'),
        (u'Tra Người Dùng ***', 'view_session_key', 'app_user/view_session_key/'),
        (u'玩家排行', 'user_power_rank', 'app_user/user_power_rank/'),
        (u'充值排行', 'user_pay_rank', 'app_user/user_pay_rank/'),
        (u'英雄排行', 'hero_power_rank', 'app_user/hero_power_rank/'),
        (u'扣除玩家道具', 'drop_user_prop', 'app_user/drop_user_prop/'),
        (u'查看扣除道具', 'drop_user_prop', 'app_user/view_drop_prop/'),


        #(u'查看军团信息', 'view_guild', 'app_user/view_guild/'),
        #(u'名称查找军团', 'view_guild_by_name', 'app_user/view_guild_by_name/'),
        (u'冻结记录', 'freeze', 'app_user/freeze_view/'),
        (u'世界聊天', 'chat_log', 'app_user/chat_log/'),
        (u'玩家私聊', 'user_msg_log', 'app_user/user_msg_log/'),
        ]},
    {'desc':u'陪玩管理','per':'MP_5','menus':[
        (u'查看模板', 'gather_player', 'gather_player/'),
        (u'模板管理', 'gather_player', 'gather_player/view_zone_gather/'),
        ]},
    {'desc':u'Waiter管理','per':'MP_4','menus':[
        (u'Waiter帐号管理', 'view_waiter', 'waiter/view_waiter/'),
        (u'Waiter帐号操作', 'waiter_game', 'waiter/waiter_game/'),
        ]},
    {'desc':u'Bug反馈','per':'MP_6','menus':[
        (u'查看记录', 'msg_view', 'msg/msg_view/'),
        (u'最新国家公告', 'msg_view', 'msg/country_notice_view/'),
    #    (u'查看用户邮件', 'msg_view_user', 'msg/msg_view_user/'),
        ]},
    #{'desc':u'冻结管理','per':'MP_7','menus':[
    #    (u'冻结记录', 'freeze', 'freeze/freeze_view/'),
    #    (u'冻结用户', 'freeze', 'freeze/freeze_user/'),
    #    ]},
    {'desc':u'充值统计','per':'MP_8','menus':[
        (u'充值记录', 'pay_record', 'pay_record/pay_record/'),
        (u'用户充值', 'pay_user_record', 'pay_record/user_record/'),
        ]},
    {'desc':u'发奖系统','per':'MP_10','menus':[
        (u'邮件发奖发送', 'reward_edit_admin', 'reward/set_reward_to_user/'),
        (u'邮件发奖查看', 'admin_gift_msg', 'reward/admin_gift_msg/'),

        (u'一般奖励添加', 'reward_edit_common', 'reward/edit_reward/'),
        (u'一般奖励查看', 'rewards', 'reward/rewards/'),

        (u'兑奖码添加', 'reward_edit_code', 'reward/edit_reward_code/'),
        (u'兑奖码查看', 'code_rewards', 'reward/code_rewards/'),

        (u'萌币发奖添加', 'send_ucoin', 'reward/add_ucoin_reward/'),
        (u'萌币发奖查看', 'send_ucoin', 'reward/view_ucoin_reward/'),

        (u'奖励查找', 'search_rewards', 'reward/search_rewards/'),

        (u'同步Server奖励', 'publish_reward', 'reward/publish_reward/'),

        #(u'走马灯添加', 'edit_push_notice', 'reward/edit_push_notice/'),
        #(u'走马灯管理', 'push_notice', 'reward/push_notice/'),
        ]},
    {'desc':u'配置发布','per':'MP_11','menus':[
        (u'配置发布', 'publish', 'publish/publish/'),
        (u'同步跨服战配置', 'publish', 'publish/publish_duplicate/'),
        ]},

]
#if settings.WHERE == 'local':
#    MENUS[4]['menus'].insert(0, (u'首次付费', 'buy_record', 'coin_record/buy_record/?first=1'))
#    MENUS[4]['menus'].insert(0,(u'消费记录', 'buy_record', 'coin_record/buy_record/'))
