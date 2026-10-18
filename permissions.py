# -*- coding:utf-8 -*-

PERMISSIONS = [
    ['logout_user', u'退出用户登录'],

    ['flash_api', u'Flash API接口'],
    ['system_setting', u'配置查看'],
    ['system_setting_p', u'正式配置编辑'],
    ['test_setting', u'测试配置编辑'],
    ['switch_setting', u'配置切换'],
    ['publish', u'配置发布'],
    ['system_setting_p2', u'运营配置修改'],
    ['update_notice', u'更新公告'],
    ['zone_manage', u'分区管理'],
    ['merge_zone', u'合服操作'],
    ['zone_maintain', u'分区维护'],
    ['gather_player', u'管理陪玩模板'],

    ['view_app_user', u'查看用户信息'],
    ['mod_app_user', u'修改用户信息'],
    ['js_test', u'JS测试'],
    ['cleanup_troops', u'清理玩家部队'],
    ['sync_invitation', u'同步分享数据'],
    ['simulate_merge', u'模拟合服结算'],
    ['view_session_key', u'昵称查找用户'],
    ['user_interim_pwd', u'生成用户临时密码'],
    ['admin_pay', u'后台充值'],
    ['weixin_admin_pay', u'生成二维码支付'],
    ['drop_user_prop', u'扣除玩家道具'],
    ['freeze', u'冻结管理'],
    ['freeze_user', u'冻结帐号'],
    ['view_world', u'查看世界信息'],
    ['view_world_report', u'查看世界年报'],
    ['init_pk_yard', u'修改世界信息'],
    ['view_duplicate', u'查看跨服战场'],
    ['user_power_rank', u'玩家排行'],
    ['user_pay_rank', u'充值排行'],
    ['hero_power_rank', u'英雄排行'],
    ['chat_log', u'世界聊天'],
    ['user_msg_log', u'玩家私聊'],

    ['msg_view', u'查看Bug反馈'],
    ['msg_view_user', u'查看用户邮件'],
    ['re_msg', u'回复Bug反馈'],
    ['change_country_notice', u'修改国家公告'],

    ['pay_record', u'充值记录'],
    ['pay_user_record', u'用户充值'],

    ['send_ucoin', u'萌币发奖'],
    ['admin_gift_msg', u'邮件发奖查看'],
    ['reward_edit_admin|1', u'邮件发奖编辑一级'],
    ['reward_edit_admin|2', u'邮件发奖编辑二级'],
    ['reward_edit_admin|3', u'邮件发奖编辑三级'],

    ['rewards', u'一般奖励查看'],
    ['reward_edit_common|1', u'一般奖励编辑一级'],
    ['reward_edit_common|2', u'一般奖励编辑二级'],
    ['reward_edit_common|3', u'一般奖励编辑三级'],

    ['code_rewards', u'兑奖码查看'],
    ['reward_edit_code|1', u'兑奖码编辑一级'],
    ['reward_edit_code|2', u'兑奖码编辑二级'],
    ['reward_edit_code|3', u'兑奖码编辑三级'],

    ['publish_reward', u'奖励配置发布'],
    ['search_rewards', u'奖励查找'],

    ['admin_waiter_pay', u'后台仅限waiter充值'],
    ['view_waiter', u'Waiter帐号管理'],
    ['edit_waiter', u'添加/修改Waiter'],
    ['waiter_game', u'Waiter操作'],

]
PERMISSION_KEYS = [p[0] for p in PERMISSIONS]
