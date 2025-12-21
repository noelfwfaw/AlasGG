from abc import ABCMeta, abstractmethod
from module.base.decorator import cached_property
from module.campaign.campaign_base import CampaignBase
from module.campaign.run import CampaignRun
from module.combat.assets import BATTLE_PREPARATION
from module.combat.emotion import Emotion
from module.equipment.assets import *
from module.equipment.equipment_code import EquipmentCodeHandler
from module.equipment.equipment_change import EquipmentChange
from module.equipment.fleet_equipment import FleetEquipment
from module.exception import CampaignEnd, ScriptEnd, ScriptError, RequestHumanTakeover
from module.handler.assets import AUTO_SEARCH_MAP_OPTION_OFF
from module.logger import logger
from module.map.assets import FLEET_PREPARATION, MAP_PREPARATION
from module.map.map_operation import MapOperation
from module.retire.assets import (
    DOCK_CHECK, DOCK_SHIP_DOWN,
    TEMPLATE_BOGUE, TEMPLATE_HERMES, TEMPLATE_LANGLEY, TEMPLATE_RANGER,
    TEMPLATE_CASSIN_1, TEMPLATE_CASSIN_2, TEMPLATE_DOWNES_1, TEMPLATE_DOWNES_2,
    TEMPLATE_AULICK, TEMPLATE_FOOTE
)
from module.equipment.equipment_code import EMPTY_GEAR_CODE
from module.retire.dock import Dock
from module.retire.scanner import ShipScanner
from module.ui.assets import BACK_ARROW
from module.ui.page import page_fleet

SIM_VALUE = 0.92


class GemsEmotion(Emotion):

    def check_reduce(self, battle):
        """
        Overwrite emotion.check_reduce()
        Check emotion before entering a campaign.

        Args:
            battle (int): Battles in this campaign

        Raise:
            CampaignEnd: Pause current task to prevent emotion control in the future.
        """
        if not self.is_calculate:
            return

        recovered, delay = self._check_reduce(battle)
        if delay:
            self.config.GEMS_EMOTION_TRIGGERED = True
            logger.info('Detect low emotion, pause current task')
            raise CampaignEnd('Emotion control')

    def wait(self, fleet_index):
        pass


class GemsCampaignOverride(CampaignBase):

    def handle_combat_low_emotion(self):
        """
        Overwrite info_handler.handle_combat_low_emotion()
        If change vanguard is enabled, withdraw combat and change flagship and vanguard
        """
        if self.config.GemsFarming_ChangeVanguard == 'disabled':
            result = self.handle_popup_confirm('IGNORE_LOW_EMOTION')
            if result:
                # Avoid clicking AUTO_SEARCH_MAP_OPTION_OFF
                self.interval_reset(AUTO_SEARCH_MAP_OPTION_OFF)
            return result

        if self.handle_popup_cancel('IGNORE_LOW_EMOTION'):
            self.config.GEMS_EMOTION_TRIGGERED = True
            logger.hr('EMOTION WITHDRAW')

            while 1:
                self.device.screenshot()

                if self.handle_story_skip():
                    continue
                if self.handle_popup_cancel('IGNORE_LOW_EMOTION'):
                    continue

                if self.appear(BATTLE_PREPARATION, offset=(20, 20), interval=2):
                    self.device.click(BACK_ARROW)
                    continue
                if self.handle_auto_search_exit():
                    continue
                if self.is_in_stage():
                    break

                if self.is_in_map():
                    self.withdraw()
                    break

                if self.appear(FLEET_PREPARATION, offset=(20, 50), interval=2) \
                        or self.appear(MAP_PREPARATION, offset=(20, 20), interval=2):
                    self.enter_map_cancel()
                    break
            raise CampaignEnd('Emotion withdraw')


class GemsEquipmentHandler(EquipmentCodeHandler):
    def __init__(self, config, device=None, task=None):
        super().__init__(config=config,
                         device=device,
                         task=task,
                         key="GemsFarming.GemsFarming.EquipmentCode",
                         ships=['DD', 'bogue', 'hermes', 'langley', 'ranger'])

    def current_ship(self, skip_first_screenshot=True):
        """
        Reuse templates in module.retire.assets,
        which needs different rescaling to match each current flagship.

        Pages:
            in: gear_code
        """
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.device.screenshot()
            
            # End
            if not self.appear(EMPTY_SHIP_R):
                break
            else:
                logger.info('Waiting ship icon loading.')
            
        if TEMPLATE_BOGUE.match(self.device.image, scaling=1.46):  # image has rotation
            return 'bogue'
        if TEMPLATE_HERMES.match(self.device.image, scaling=124/89):
            return 'hermes'
        if TEMPLATE_RANGER.match(self.device.image, scaling=4/3):
            return 'ranger'
        if TEMPLATE_LANGLEY.match(self.device.image, scaling=25/21):
            return 'langley'
        return 'DD'


# 从别人代码中整合的 ShipChange 基类及相关类
class ShipChange(CampaignRun, Dock, EquipmentChange, metaclass=ABCMeta):
    # Will be overridden in NormalShipChange and HardShipChange
    fleet_to_attack: int
    page_fleet_check_button: Button
    flagship_detail_enter: Button
    vanguard_detail_enter: Button
    flagship_enter: Button
    vanguard_enter: Button

    @abstractmethod
    def fleet_enter(self):
        pass

    @abstractmethod
    def fleet_enter_ship(self, button):
        pass

    @abstractmethod
    def fleet_back(self):
        pass

    @abstractmethod
    def dock_ship_down(self, button):
        pass

    @abstractmethod
    def after_flagship_change_failed(self):
        pass

    @abstractmethod
    def after_vanguard_change_failed(self):
        pass

    @property
    def change_flagship_equip(self):
        return 'equip' in self.config.GemsFarming_ChangeFlagship

    @property
    def change_vanguard_equip(self):
        return 'equip' in self.config.GemsFarming_ChangeVanguard

    def flagship_change(self):
        """
        Change flagship and flagship's equipment
        If config.GemsFarming_CommonCV == 'any', only change auxiliary equipment

        Returns:
            bool: True if flagship changed.
        """

        if self.config.GemsFarming_CommonCV == 'any':
            index_list = range(3, 5)
        else:
            index_list = range(0, 5)
        logger.hr('Change flagship', level=1)
        logger.attr('ChangeFlagship', self.config.GemsFarming_ChangeFlagship)
        self.fleet_enter()
        if self.change_flagship_equip:
            logger.hr('Record flagship equipment', level=2)
            self.fleet_enter_ship(self.flagship_detail_enter)
            self.ship_equipment_record_image(index_list=index_list)
            self.ship_equipment_take_off()
            self.fleet_back()

        logger.hr('Change flagship', level=2)
        success = self.flagship_change_execute()

        if self.change_flagship_equip:
            logger.hr('Equip flagship equipment', level=2)
            self.fleet_enter_ship(self.flagship_detail_enter)
            self.ship_equipment_take_off()
            self.ship_equipment_take_on_image(index_list=index_list)
            self.fleet_back()

        return success

    def vanguard_change(self):
        """
        Change vanguard and vanguard's equipment

        Returns:
            bool: True if vanguard changed
        """

        logger.hr('Change vanguard', level=1)
        logger.attr('ChangeVanguard', self.config.GemsFarming_ChangeVanguard)
        self.fleet_enter()
        if self.change_vanguard_equip:
            logger.hr('Record vanguard equipment', level=2)
            self.fleet_enter_ship(self.vanguard_detail_enter)
            self.ship_equipment_record_image()
            self.ship_equipment_take_off()
            self.fleet_back()

        logger.hr('Change vanguard', level=2)
        success = self.vanguard_change_execute()

        if self.change_vanguard_equip:
            logger.hr('Equip vanguard equipment', level=2)
            self.fleet_enter_ship(self.vanguard_detail_enter)
            self.ship_equipment_take_off()
            self.ship_equipment_take_on_image()
            self.fleet_back()

        return success

    def _dock_reset(self):
        self.dock_favourite_set(False, wait_loading=False)
        self.dock_sort_method_dsc_set(wait_loading=False)
        self.dock_filter_set()

    def _ship_change_confirm(self, button):
        self.dock_select_one(button)
        self._dock_reset()
        self.dock_select_confirm(check_button=self.page_fleet_check_button)

    def get_common_rarity_cv(self, level=31, emotion=10):
        """
        Get a common rarity cv by config.GemsFarming_CommonCV
        If config.GemsFarming_CommonCV == 'any', return a common lv1 ~ lv33 cv

        _dock_reset() needs to be called later.

        Returns:
            Ship:
        """
        self.dock_favourite_set(False, wait_loading=False)
        self.dock_sort_method_dsc_set(False, wait_loading=False)
        self.dock_filter_set(
            index='cv', rarity='common', extra='enhanceable', sort='total')

        logger.hr('FINDING FLAGSHIP')

        scanner = ShipScanner(level=(1, level), emotion=(emotion, 150),
                              fleet=self.fleet_to_attack, status='free')
        scanner.disable('rarity')

        if self.config.GemsFarming_CommonCV == 'any':

            ships = scanner.scan(self.device.image)
            if ships:
                # Don't need to change current
                return ships

            # Change to any ship
            scanner.set_limitation(fleet=0)
            return scanner.scan(self.device.image, output=False)

        else:
            template = {
                'BOGUE': TEMPLATE_BOGUE,
                'HERMES': TEMPLATE_HERMES,
                'LANGLEY': TEMPLATE_LANGLEY,
                'RANGER': TEMPLATE_RANGER
            }[f'{self.config.GemsFarming_CommonCV.upper()}']

            ships = scanner.scan(self.device.image)
            if ships:
                # Don't need to change current
                return ships

            scanner.set_limitation(fleet=0)
            candidates = [ship for ship in scanner.scan(self.device.image, output=False)
                          if template.match(self.image_crop(ship.button, copy=False), similarity=SIM_VALUE)]

            if candidates:
                # Change to specific ship
                return candidates

            logger.info('No specific CV was found, try reversed order.')
            self.dock_sort_method_dsc_set(True)

            candidates = [ship for ship in scanner.scan(self.device.image)
                          if template.match(self.image_crop(ship.button, copy=False), similarity=SIM_VALUE)]

            return candidates

    def get_common_rarity_dd(self, emotion=10):
        """
        Get a common rarity dd with level is 100 (70 for servers except CN) and emotion > 10

        _dock_reset() needs to be called later.

        Returns:
            Ship:
        """
        if self.config.GemsFarming_CommonDD == 'any':
            faction = ['eagle', 'iron']
        elif self.config.GemsFarming_CommonDD == 'favourite':
            faction = 'all'
        elif self.config.GemsFarming_CommonDD == 'z20_or_z21':
            faction = 'iron'
        elif self.config.GemsFarming_CommonDD in ['aulick_or_foote', 'cassin_or_downes']:
            faction = 'eagle'
        else:
            logger.error(f'Invalid CommonDD setting: {self.config.GemsFarming_CommonDD}')
            raise ScriptError('Invalid GemsFarming_CommonDD')
        favourite = self.config.GemsFarming_CommonDD == 'favourite'
        self.dock_favourite_set(favourite, wait_loading=False)
        self.dock_sort_method_dsc_set(True, wait_loading=False)
        self.dock_filter_set(
            index='dd', rarity='common', faction=faction, extra='can_limit_break')

        logger.hr('FINDING VANGUARD')

        if self.config.SERVER in ['cn']:
            max_level = 100
        else:
            max_level = 70

        scanner = ShipScanner(level=(max_level, max_level), emotion=(emotion, 150),
                              fleet=self.fleet_to_attack, status='free')
        scanner.disable('rarity')

        ships = scanner.scan(self.device.image)
        if ships:
            # Don't need to change current
            return ships

        scanner.set_limitation(fleet=0)
        if self.config.GemsFarming_CommonDD in ['any', 'favourite', 'z20_or_z21']:
            # Change to any ship
            return scanner.scan(self.device.image, output=False)

        candidates = self.find_candidates(self.get_templates(self.config.GemsFarming_CommonDD), scanner)

        if candidates:
            # Change to specific ship
            return candidates

        logger.info('No specific DD was found, try reversed order.')
        self.dock_sort_method_dsc_set(False)

        # Change specific ship
        candidates = self.find_candidates(self.get_templates(self.config.GemsFarming_CommonDD), scanner)
        return candidates

    def find_candidates(self, template, scanner):
        """
        Find candidates based on template matching using a scanner.

        """
        candidates = []
        for item in template:
            candidates = [ship for ship in scanner.scan(self.device.image, output=False)
                          if item.match(self.image_crop(ship.button, copy=False), similarity=SIM_VALUE)]
            if candidates:
                break
        return candidates

    @staticmethod
    def get_templates(common_dd):
        """
        Returns the corresponding template list based on CommonDD
        """
        if common_dd == 'aulick_or_foote':
            return [
                TEMPLATE_AULICK,
                TEMPLATE_FOOTE
            ]
        elif common_dd == 'cassin_or_downes':
            return [
                TEMPLATE_CASSIN_1, TEMPLATE_CASSIN_2,
                TEMPLATE_DOWNES_1, TEMPLATE_DOWNES_2
            ]
        else:
            logger.error(f'Invalid CommonDD setting: {common_dd}')
            raise ScriptError(f'Invalid CommonDD setting: {common_dd}')

    def flagship_change_execute(self):
        """
        Returns:
            bool: If success.

        Pages:
            in: page_fleet
            out: page_fleet
        """
        self.dock_ship_down(self.flagship_detail_enter)
        self.ui_click(self.flagship_enter,
                      appear_button=self.page_fleet_check_button, check_button=DOCK_CHECK, skip_first_screenshot=True)

        ship = self.get_common_rarity_cv()
        if ship:
            self._ship_change_confirm(min(ship, key=lambda s: (s.level, -s.emotion)).button)

            logger.info('Change flagship success')
            return True
        else:
            logger.info('Change flagship failed, no CV in common rarity.')
            self.after_flagship_change_failed()
            return False

    def vanguard_change_execute(self):
        """
        Returns:
            bool: If success.

        Pages:
            in: page_fleet
            out: page_fleet
        """
        self.dock_ship_down(self.vanguard_detail_enter)
        self.ui_click(self.vanguard_enter,
                      appear_button=self.page_fleet_check_button, check_button=DOCK_CHECK, skip_first_screenshot=True)

        ship = self.get_common_rarity_dd()
        if ship:
            self._ship_change_confirm(max(ship, key=lambda s: s.emotion).button)

            logger.info('Change vanguard ship success')
            return True
        else:
            logger.info('Change vanguard ship failed, no DD in common rarity.')
            self.after_vanguard_change_failed()
            return False


class NormalShipChange(FleetEquipment, ShipChange):
    @property
    def fleet_to_attack(self):
        if self.config.Fleet_FleetOrder == 'fleet1_standby_fleet2_all':
            return self.config.Fleet_Fleet2
        else:
            return self.config.Fleet_Fleet1

    @property
    def page_fleet_check_button(self):
        return page_fleet.check_button

    @property
    def flagship_detail_enter(self):
        return FLEET_DETAIL_ENTER_FLAGSHIP

    @property
    def vanguard_detail_enter(self):
        return FLEET_DETAIL_ENTER

    @property
    def flagship_enter(self):
        return FLEET_ENTER_FLAGSHIP

    @property
    def vanguard_enter(self):
        return FLEET_ENTER

    def fleet_enter(self):
        super().fleet_enter(self.fleet_to_attack)

    def fleet_enter_ship(self, button):
        super().fleet_enter_ship(button)

    def fleet_back(self):
        super().fleet_back()

    def dock_ship_down(self, button):
        """
        Don't need to down ship in normal mode
        """
        pass

    def after_flagship_change_failed(self):
        self._dock_reset()
        self.ui_back(check_button=page_fleet.check_button)

    def after_vanguard_change_failed(self):
        self.after_flagship_change_failed()


class HardShipChange(MapOperation, ShipChange):
    def __init__(self, campaign=None, stage=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.campaign: CampaignBase = campaign
        self.config = self.campaign.config
        self.stage: str = stage

    @property
    def fleet_to_attack(self):
        return 2 if self.config.Fleet_FleetOrder == 'fleet1_standby_fleet2_all' else 1

    @property
    def page_fleet_check_button(self):
        return FLEET_PREPARATION

    @property
    def flagship_detail_enter(self):
        return globals()[f'FLEET_DETAIL_ENTER_FLAGSHIP_HARD_{self.fleet_to_attack}']

    @property
    def vanguard_detail_enter(self):
        return globals()[f'FLEET_DETAIL_ENTER_HARD_{self.fleet_to_attack}']

    @property
    def flagship_enter(self):
        return globals()[f'FLEET_ENTER_FLAGSHIP_HARD_{self.fleet_to_attack}']

    @property
    def vanguard_enter(self):
        return globals()[f'FLEET_ENTER_HARD_{self.fleet_to_attack}']

    def fleet_enter(self):
        if self.appear(FLEET_PREPARATION, offset=(20, 50)):
            return
        self.campaign.ensure_campaign_ui(self.stage)
        self.ui_click(click_button=self.campaign.ENTRANCE,
                      appear_button=BACK_ARROW, check_button=MAP_PREPARATION)
        while 1:
            self.device.screenshot()

            if self.handle_map_mode_switch('hard') and self.appear_then_click(MAP_PREPARATION, interval=1):
                continue

            if self.handle_retirement():
                continue

            if self.appear(FLEET_PREPARATION, offset=(20, 50)):
                break

    def fleet_enter_ship(self, button):
        self.ship_info_enter(button)

    def fleet_back(self):
        self.ui_back(FLEET_PREPARATION)

    def dock_ship_down(self, button):
        """
        In hard mode, let the ship leave the fleet first
        """
        self.ui_click(button,
                        appear_button=FLEET_PREPARATION, check_button=DOCK_CHECK, skip_first_screenshot=True)
        if self.appear(DOCK_SHIP_DOWN):
            self.ui_click(DOCK_SHIP_DOWN,
                            appear_button=DOCK_CHECK, check_button=FLEET_PREPARATION, skip_first_screenshot=True)
        else:
            self.ui_back(check_button=FLEET_PREPARATION)

    def after_flagship_change_failed(self):
        """
        In hard mode, should still put a ship in the fleet if there is no available ship
        """
        max_level = 100 if self.config.SERVER in ['cn'] else 70
        ship = self.get_common_rarity_cv(level=max_level, emotion=0)
        if ship:
            self._ship_change_confirm(min(ship, key=lambda s: (s.level, -s.emotion)).button)
        else:
            raise RequestHumanTakeover
        
    def after_vanguard_change_failed(self):
        """
        In hard mode, should still put a ship in the fleet if there is no available ship
        """
        ship = self.get_common_rarity_dd(emotion=0)
        if ship:
            self._ship_change_confirm(max(ship, key=lambda s: s.emotion).button)
        else:
            raise RequestHumanTakeover

    def flagship_change_execute(self):
        """
        Returns:
            bool: If success.

        Pages:
            in: page_fleet
            out: page_fleet
        """
        self.dock_ship_down(self.flagship_detail_enter)
        self.ui_click(self.flagship_enter,
                      appear_button=self.page_fleet_check_button, check_button=DOCK_CHECK, skip_first_screenshot=True)

        ship = self.get_common_rarity_cv()
        if ship:
            target_ship = min(ship, key=lambda s: (s.level, -s.emotion))
            # === 新增：更新情感值 ===
            self._update_emotion(target_ship.emotion, is_flagship=True)
            self._ship_change_confirm(target_ship.button)

            logger.info('Change flagship success')
            return True
        else:
            logger.info('Change flagship failed, no CV in common rarity.')
            self.after_flagship_change_failed()
            return False

    def vanguard_change_execute(self):
        """
        Returns:
            bool: If success.

        Pages:
            in: page_fleet
            out: page_fleet
        """
        self.dock_ship_down(self.vanguard_detail_enter)
        self.ui_click(self.vanguard_enter,
                      appear_button=self.page_fleet_check_button, check_button=DOCK_CHECK, skip_first_screenshot=True)

        ship = self.get_common_rarity_dd()
        if ship:
            target_ship = max(ship, key=lambda s: s.emotion)
            # === 新增：更新情感值 ===
            self._update_emotion(target_ship.emotion, is_flagship=False)
            self._ship_change_confirm(target_ship.button)

            logger.info('Change vanguard ship success')
            return True
        else:
            logger.info('Change vanguard ship failed, no DD in common rarity.')
            self.after_vanguard_change_failed()
            return False
    
    def _update_emotion(self, emotion, is_flagship=True):
        """更新配置中的情感值"""
        if is_flagship:
            # 更新旗舰情感值（通常使用舰队1的情感值）
            if self.config.Fleet_FleetOrder == 'fleet1_standby_fleet2_all':
                self.config.set_record(Emotion_Fleet2Value=emotion)
            else:
                self.config.set_record(Emotion_Fleet1Value=emotion)
        else:
            # 更新先锋情感值（通常使用舰队2的情感值）
            if self.config.Fleet_FleetOrder == 'fleet1_standby_fleet2_all':
                self.config.set_record(Emotion_Fleet1Value=emotion)
            else:
                # 在普通配置中，可能没有单独记录先锋情感值
                # 这里简化处理，假设旗舰和先锋在同一舰队
                pass
        logger.info(f'更新情感值: {emotion} ({"旗舰" if is_flagship else "先锋"})')

class HardShipChangeWithEquipmentCode(HardShipChange, GemsEquipmentHandler):
    """困难模式换船，使用装备码换装备"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        GemsEquipmentHandler.__init__(self, config=self.config, device=self.device, task=None)
    
    def _ensure_equipment_code_accessible(self):
        """确保可以访问装备码页面"""
        # 在困难模式下，可能需要额外的步骤来进入装备码页面
        # 首先确保我们在船详情页面
        if not self.appear(EQUIPMENT_CODE_ENTRANCE, offset=(5, 5)):
            # 如果看不到装备码入口，可能需要点击其他按钮
            # 检查是否在正确的页面
            logger.info('在困难模式下寻找装备码入口')
            # 尝试查找并点击装备码入口
            if self.appear_then_click(EQUIPMENT_CODE_ENTRANCE, offset=(5, 5), interval=2):
                return True
            # 如果还是找不到，可能需要后退或进行其他操作
            logger.warning('在困难模式下未找到装备码入口')
            return False
        return True
    
    def clear_all_equip(self):
        """清空所有装备 - 适配困难模式"""
        logger.info('在困难模式下清空装备')
        
        # 确保可以访问装备码页面
        if not self._ensure_equipment_code_accessible():
            logger.error('无法访问装备码页面')
            return False
        
        # 调用父类的 clear_all_equip 方法
        try:
            # 进入装备码页面
            self.enter_equip_code_page()
            ship = self.current_ship()
            logger.info(f'当前船型: {ship}')
            
            # 设置输入法
            self.device.u2_set_fastinput_ime(True)
            logger.attr("Current_ime", self.device.u2_current_ime())
            
            # 点击导出按钮
            self.click_export_button()
            
            # 如果该船没有装备码，则导出当前装备码
            if self.codes.__getattribute__(ship) is None:
                self.export_equip_code(ship)
            
            # 清空装备预览
            self.clear_equip_preview()
            
            # 确认清空装备
            for attempt in range(5):
                success = self.confirm_equip_preview()
                if success:
                    logger.info('清空装备成功')
                    return True
                else:
                    self.handle_storage_full()
                    self.clear_equip_preview()
            
            logger.error('清空装备失败，达到最大重试次数')
            return False
            
        except Exception as e:
            logger.error(f'清空装备时发生错误: {e}')
            return False
    
    def apply_equip_code(self, code=None):
        """应用装备码 - 适配困难模式"""
        logger.info('在困难模式下应用装备码')
        
        # 确保可以访问装备码页面
        if not self._ensure_equipment_code_accessible():
            logger.error('无法访问装备码页面')
            return False
        
        try:
            # 进入装备码页面
            self.enter_equip_code_page()
            
            # 清空装备预览
            self.clear_equip_preview()
            
            # 获取或使用指定的装备码
            if code is None:
                ship = self.current_ship()
                code = self.codes.__getattribute__(ship)
                if code is None:
                    code = self.device.clipboard
                logger.info(f'为 {ship} 应用装备码: {code}')
            else:
                logger.info(f'强制应用装备码: {code}')
            
            # 应用装备码
            for attempt in range(5):
                if code is not None and code != EMPTY_GEAR_CODE:
                    # 进入输入模式
                    self.enter_equip_code_input_mode()
                    # 输入装备码
                    self.device.text_input_and_confirm(code, clear=True)
                    # 确认装备码
                    success = self.confirm_equip_code()
                    if not success:
                        continue
                
                # 确认装备预览
                success = self.confirm_equip_preview()
                if success:
                    logger.info('装备码应用成功')
                    return True
                else:
                    self.handle_storage_full()
                    self.clear_equip_preview()
            
            logger.error('应用装备码失败，达到最大重试次数')
            return False
            
        except Exception as e:
            logger.error(f'应用装备码时发生错误: {e}')
            return False
    
    def flagship_change(self):
        """重写旗舰更换方法，使用装备码逻辑"""
        logger.hr('Change flagship', level=1)
        logger.attr('ChangeFlagship', self.config.GemsFarming_ChangeFlagship)
        
        # 进入舰队页面
        self.fleet_enter()
        
        if self.change_flagship_equip:
            logger.hr('Unmount flagship equipments', level=2)
            self.fleet_enter_ship(self.flagship_detail_enter)
            # 使用适配后的清空装备方法
            success = self.clear_all_equip()
            if not success:
                logger.warning('清空旗舰装备失败，继续换船')
            self.fleet_back()

        logger.hr('Change flagship', level=2)
        success = self.flagship_change_execute()

        if self.change_flagship_equip and success:
            logger.hr('Mount flagship equipments', level=2)
            self.fleet_enter_ship(self.flagship_detail_enter)
            # 使用适配后的应用装备码方法
            success_equip = self.apply_equip_code()
            if not success_equip:
                logger.warning('安装旗舰装备失败')
            self.fleet_back()
            # 如果装备安装失败，仍然认为换船成功
            return success

        return success
    
    def vanguard_change(self):
        """重写先锋更换方法，使用装备码逻辑"""
        logger.hr('Change vanguard', level=1)
        logger.attr('ChangeVanguard', self.config.GemsFarming_ChangeVanguard)
        
        # 进入舰队页面
        self.fleet_enter()
        
        if self.change_vanguard_equip:
            logger.hr('Unmount vanguard equipments', level=2)
            self.fleet_enter_ship(self.vanguard_detail_enter)
            # 使用适配后的清空装备方法
            success = self.clear_all_equip()
            if not success:
                logger.warning('清空先锋装备失败，继续换船')
            self.fleet_back()

        logger.hr('Change vanguard', level=2)
        success = self.vanguard_change_execute()

        if self.change_vanguard_equip and success:
            logger.hr('Mount vanguard equipments', level=2)
            self.fleet_enter_ship(self.vanguard_detail_enter)
            # 使用适配后的应用装备码方法
            success_equip = self.apply_equip_code()
            if not success_equip:
                logger.warning('安装先锋装备失败')
            self.fleet_back()
            # 如果装备安装失败，仍然认为换船成功
            return success

        return success

class GemsFarming(CampaignRun, Dock, FleetEquipment, GemsEquipmentHandler):

    def load_campaign(self, name, folder='campaign_main'):
        super().load_campaign(name, folder)

        class GemsCampaign(GemsCampaignOverride, self.module.Campaign):
            
            @cached_property
            def emotion(self) -> GemsEmotion:
                return GemsEmotion(config=self.config)

        self.campaign = GemsCampaign(device=self.campaign.device, config=self.campaign.config)
        if self.change_flagship or self.change_vanguard:
            self.campaign.config.override(Emotion_Mode='ignore_calculate')
        else:
            self.campaign.config.override(Emotion_Mode='ignore')
        self.campaign.config.override(EnemyPriority_EnemyScaleBalanceWeight='S1_enemy_first')

    @property
    def emotion_lower_bound(self):
        return 4 + self.campaign._map_battle * 2

    @property
    def change_flagship(self):
        return 'ship' in self.config.GemsFarming_ChangeFlagship

    @property
    def change_flagship_equip(self):
        return 'equip' in self.config.GemsFarming_ChangeFlagship

    @property
    def change_vanguard(self):
        return 'ship' in self.config.GemsFarming_ChangeVanguard

    @property
    def change_vanguard_equip(self):
        return 'equip' in self.config.GemsFarming_ChangeVanguard

    @property
    def fleet_to_attack(self):
        if self.config.Fleet_FleetOrder == 'fleet1_standby_fleet2_all':
            return self.config.Fleet_Fleet2
        else:
            return self.config.Fleet_Fleet1

    # 以下是你的普通模式换船方法，保持不变
    def flagship_change(self):
        """
        Change flagship and flagship's equipment using gear code

        Returns:
            bool: True if flagship changed.
        """

        logger.hr('Change flagship', level=1)
        logger.attr('ChangeFlagship', self.config.GemsFarming_ChangeFlagship)
        self.fleet_enter(self.fleet_to_attack)
        if self.change_flagship_equip:
            logger.hr('Unmount flagship equipments', level=2)
            self.fleet_enter_ship(FLEET_DETAIL_ENTER_FLAGSHIP)
            self.clear_all_equip()
            self.fleet_back()

        logger.hr('Change flagship', level=2)
        success = self.flagship_change_execute()

        if self.change_flagship_equip:
            logger.hr('Mount flagship equipments', level=2)
            self.fleet_enter_ship(FLEET_DETAIL_ENTER_FLAGSHIP)
            self.apply_equip_code()
            self.fleet_back()

        return success

    def vanguard_change(self):
        """
        Change vanguard and vanguard's equipment using gear code

        Returns:
            bool: True if vanguard changed
        """
        logger.hr('Change vanguard', level=1)
        logger.attr('ChangeVanguard', self.config.GemsFarming_ChangeVanguard)
        self.fleet_enter(self.fleet_to_attack)
        if self.change_vanguard_equip:
            logger.hr('Unmount vanguard equipments', level=2)
            self.fleet_enter_ship(FLEET_DETAIL_ENTER)
            self.clear_all_equip()
            self.fleet_back()

        logger.hr('Change vanguard', level=2)
        success = self.vanguard_change_execute()

        if self.change_vanguard_equip:
            logger.hr('Mount vanguard equipments', level=2)
            self.fleet_enter_ship(FLEET_DETAIL_ENTER)
            self.apply_equip_code()
            self.fleet_back()

        return success

    def _dock_reset(self):
        self.dock_favourite_set(False, wait_loading=False)
        self.dock_sort_method_dsc_set(wait_loading=False)
        self.dock_filter_set()

    def _ship_change_confirm(self, button):
        self.dock_select_one(button)
        self._dock_reset()
        self.dock_select_confirm(check_button=page_fleet.check_button)

    def get_common_rarity_cv(self):
        """
        Get a common rarity cv by config.GemsFarming_CommonCV
        If config.GemsFarming_CommonCV == 'any', return a common lv1 ~ lv33 cv

        _dock_reset() needs to be called later.

        Returns:
            Ship:
        """
        self.dock_favourite_set(False, wait_loading=False)
        self.dock_sort_method_dsc_set(False, wait_loading=False)
        self.dock_filter_set(
            index='cv', rarity='common', extra='enhanceable', sort='total')

        logger.hr('FINDING FLAGSHIP')

        scanner = ShipScanner(level=(1, 31), 
                              emotion=(self.emotion_lower_bound, 150),
                              fleet=self.fleet_to_attack, status='free')
        scanner.disable('rarity')

        if self.config.GemsFarming_CommonCV == 'any':

            ships = scanner.scan(self.device.image)
            if ships:
                # Don't need to change current
                return ships

            # Change to any ship
            scanner.set_limitation(fleet=0)
            return scanner.scan(self.device.image, output=False)

        else:
            template = {
                'BOGUE': TEMPLATE_BOGUE,
                'HERMES': TEMPLATE_HERMES,
                'LANGLEY': TEMPLATE_LANGLEY,
                'RANGER': TEMPLATE_RANGER
            }[f'{self.config.GemsFarming_CommonCV.upper()}']

            ships = scanner.scan(self.device.image)
            if ships:
                # Don't need to change current
                return ships

            scanner.set_limitation(fleet=0)
            candidates = [ship for ship in scanner.scan(self.device.image, output=False)
                          if template.match(self.image_crop(ship.button, copy=False), similarity=SIM_VALUE)]

            if candidates:
                # Change to specific ship
                return candidates

            logger.info('No specific CV was found, try reversed order.')
            self.dock_sort_method_dsc_set(True)

            candidates = [ship for ship in scanner.scan(self.device.image)
                          if template.match(self.image_crop(ship.button, copy=False), similarity=SIM_VALUE)]

            return candidates

    def get_common_rarity_dd(self):
        """
        Get a common rarity dd with level is 100 (70 for servers except CN) 
        and emotion >= self.emotion_lower_bound
        _dock_reset() needs to be called later.

        Returns:
            Ship:
        """
        if self.config.GemsFarming_CommonDD == 'any':
            faction = ['eagle', 'iron']
        elif self.config.GemsFarming_CommonDD == 'favourite':
            faction = 'all'
        elif self.config.GemsFarming_CommonDD == 'z20_or_z21':
            faction = 'iron'
        elif self.config.GemsFarming_CommonDD in ['aulick_or_foote', 'cassin_or_downes']:
            faction = 'eagle'
        else:
            logger.error(f'Invalid CommonDD setting: {self.config.GemsFarming_CommonDD}')
            raise ScriptError('Invalid GemsFarming_CommonDD')

        favourite = self.config.GemsFarming_CommonDD == 'favourite'
        self.dock_favourite_set(favourite, wait_loading=False)
        self.dock_sort_method_dsc_set(True, wait_loading=False)
        self.dock_filter_set(
            index='dd', rarity='common', faction=faction, extra='can_limit_break')

        logger.hr('FINDING VANGUARD')

        if self.config.SERVER in ['cn']:
            max_level = 100
        else:
            max_level = 70

        scanner = ShipScanner(level=(max_level, max_level), 
                              emotion=(self.emotion_lower_bound, 150),
                              fleet=[0, self.fleet_to_attack], status='free')

        scanner.disable('rarity')

        if self.config.GemsFarming_CommonDD in ['any', 'favourite', 'z20_or_z21']:
            # Change to any ship
            return scanner.scan(self.device.image)

        candidates = self.find_candidates(self.get_templates(self.config.GemsFarming_CommonDD), scanner)
        if candidates:
            # Change to specific ship
            return candidates

        logger.info('No specific DD was found, try reversed order.')
        self.dock_sort_method_dsc_set(False)

        # Change specific ship
        candidates = self.find_candidates(self.get_templates(self.config.GemsFarming_CommonDD), scanner)
        return candidates

    def find_candidates(self, template, scanner):
        """
        Find candidates based on template matching using a scanner.

        """
        candidates = []
        for item in template:
            candidates = [ship for ship in scanner.scan(self.device.image, output=False)
                          if item.match(self.image_crop(ship.button, copy=False), similarity=SIM_VALUE)]
            if candidates:
                break
        return candidates

    @staticmethod
    def get_templates(common_dd):
        """
        Returns the corresponding template list based on CommonDD
        """
        if common_dd == 'aulick_or_foote':
            return [
                TEMPLATE_AULICK,
                TEMPLATE_FOOTE
            ]
        elif common_dd == 'cassin_or_downes':
            return [
                TEMPLATE_CASSIN_1, TEMPLATE_CASSIN_2,
                TEMPLATE_DOWNES_1, TEMPLATE_DOWNES_2
            ]
        else:
            logger.error(f'Invalid CommonDD setting: {common_dd}')
            raise ScriptError(f'Invalid CommonDD setting: {common_dd}')

    def flagship_change_execute(self):
        """
        Returns:
            bool: If success.

        Pages:
            in: page_fleet
            out: page_fleet
        """
        for _ in self.loop():
            if self.appear(DOCK_CHECK, offset=(20, 20)):
                break
            if self.ui_page_appear(page_fleet, interval=5):
                self.device.click(FLEET_ENTER_FLAGSHIP)
                continue
            # 2025.05.29 game tips that infos skin feature when you enter dock
            if self.handle_game_tips():
                return True

        ship = self.get_common_rarity_cv()
        if ship:
            target_ship = min(ship, key=lambda s: (s.level, -s.emotion))
            self.set_emotion(target_ship.emotion)
            self._ship_change_confirm(target_ship.button)

            logger.info('Change flagship success')
            return True
        else:
            logger.info('Change flagship failed, no CV in common rarity.')
            self._dock_reset()
            self.ui_back(check_button=page_fleet.check_button)
            return False

    def vanguard_change_execute(self):
        """
        Returns:
            bool: If success.

        Pages:
            in: page_fleet
            out: page_fleet
        """
        for _ in self.loop():
            if self.appear(DOCK_CHECK, offset=(20, 20)):
                break
            if self.ui_page_appear(page_fleet, interval=5):
                self.device.click(FLEET_ENTER)
                continue
            # 2025.05.29 game tips that infos skin feature when you enter dock
            if self.handle_game_tips():
                return True

        ship = self.get_common_rarity_dd()
        if ship:
            target_ship = max(ship, key=lambda s: s.emotion)
            self.set_emotion(min(self.get_emotion(), target_ship.emotion))
            self._ship_change_confirm(target_ship.button)

            logger.info('Change vanguard ship success')
            return True
        else:
            logger.info('Change vanguard ship failed, no DD in common rarity.')
            self.set_emotion(0)  # a failure in vanguard change means low emotion DD, assuming 0.
            self._dock_reset()
            self.ui_back(check_button=page_fleet.check_button)
            return False

    _trigger_lv32 = False
    _trigger_emotion = False

    def triggered_stop_condition(self, oil_check=True):
        # Lv32 limit
        if self.change_flagship and self.campaign.config.LV32_TRIGGERED:
            self._trigger_lv32 = True
            logger.hr('TRIGGERED LV32 LIMIT')
            return True

        if self.campaign.config.GEMS_EMOTION_TRIGGERED:

            self._trigger_emotion = True
            logger.hr('TRIGGERED EMOTION LIMIT')
            return True

        return super().triggered_stop_condition(oil_check=oil_check)

    def get_emotion(self):
        if self.config.Fleet_FleetOrder == 'fleet1_standby_fleet2_all':
            return self.campaign.config.Emotion_Fleet2Value
        else:
            return self.campaign.config.Emotion_Fleet1Value

    def set_emotion(self, emotion):
        if self.config.Fleet_FleetOrder == 'fleet1_standby_fleet2_all':
            self.campaign.config.set_record(Emotion_Fleet2Value=emotion)
        else:
            self.campaign.config.set_record(Emotion_Fleet1Value=emotion)

def run(self, name, folder='campaign_main', mode='normal', total=0):
    """
    Args:
        name (str): Name of .py file.
        folder (str): Name of the file folder under campaign.
        mode (str): `normal` or `hard`
        total (int):
    """
    self.config.STOP_IF_REACH_LV32 = self.change_flagship
    
    # 记录传入的参数
    logger.info(f'run() 传入参数: name={name}, folder={folder}, mode={mode}, total={total}')
    
    # 自动判断困难模式
    original_mode = mode
    if mode != 'hard':
        # D1, D2, D3, D4 等通常是困难模式
        if name.startswith('D') and name[1:].isdigit():
            mode = 'hard'
            logger.info(f'根据地图名称 {name} 自动设置为困难模式（原模式：{original_mode}）')
        # 其他可能表示困难模式的命名
        elif 'hard' in name.lower() or 'h' in name.lower():
            mode = 'hard'
            logger.info(f'根据地图名称 {name} 自动设置为困难模式（原模式：{original_mode}）')
    
    # 保存当前模式
    self.current_mode = mode
    self.config.Campaign_Mode = mode
    logger.info(f'最终使用的模式：{mode}')

    while 1:
        self._trigger_lv32 = False
        is_limit = self.config.StopCondition_RunCount

        try:
            super().run(name=name, folder=folder, total=total)
        except CampaignEnd as e:
            if e.args[0] in ['Emotion withdraw', 'Emotion control']:
                self._trigger_emotion = True
            else:
                raise e

        # End
        if self._trigger_lv32 or self._trigger_emotion:
            success = True
            
            # === 关键修改：根据最终模式选择换船方式 ===
            logger.info(f'触发换船，当前模式：{self.current_mode}')
            if self.current_mode == 'hard':
                # 困难模式使用 HardShipChangeWithEquipmentCode
                logger.info('使用困难模式换船逻辑（装备码版）')
                ship_change = HardShipChangeWithEquipmentCode(
                    config=self.config, 
                    device=self.device, 
                    campaign=self.campaign, 
                    stage=self.stage
                )
                if self.change_flagship:
                    success = ship_change.flagship_change()
                if self.change_vanguard:
                    success = success and ship_change.vanguard_change()
                
                # 换船成功后重置情感值为高值
                if success:
                    logger.info('换船成功，重置情感值')
                    if self.config.Fleet_FleetOrder == 'fleet1_standby_fleet2_all':
                        self.config.set_record(Emotion_Fleet1Value=150)
                        self.config.set_record(Emotion_Fleet2Value=150)
                    else:
                        self.config.set_record(Emotion_Fleet1Value=150)
            else:
                # 普通模式使用你自己的换船逻辑
                logger.info('使用普通模式换船逻辑')
                if self.change_flagship:
                    success = self.flagship_change()
                if self.change_vanguard:
                    success = success and self.vanguard_change()

            if is_limit and self.config.StopCondition_RunCount <= 0:
                logger.hr('Triggered stop condition: Run count')
                self.config.StopCondition_RunCount = 0
                self.config.Scheduler_Enable = False
                break

            self._trigger_lv32 = False
            self._trigger_emotion = False
            self.campaign.config.LV32_TRIGGERED = False
            self.campaign.config.GEMS_EMOTION_TRIGGERED = False
            
            # 换船后延迟一下
            self.device.sleep(1)

            # Scheduler
            if self.config.task_switched():
                self.campaign.ensure_auto_search_exit()
                self.config.task_stop()
            elif not success:
                self.campaign.ensure_auto_search_exit()
                self.config.task_delay(minute=30)
                self.config.task_stop()

            continue
        else:
            break