VERSION = "1.0.0-release"

import pyautogui
import time
import winsound
import json
import os
from PIL import ImageGrab, ImageDraw
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import numpy as np
from datetime import datetime
from pynput import keyboard, mouse
import threading

class StoneWashHelper:
    CONFIG_FILE = "config.json"

    def __init__(self):
        # 颜色定义 (RGB)
        self.RED_COLOR = (220, 35, 85)
        self.COLOR_TOLERANCE = 30

        # 存储区域和位置
        self.wash_button_pos = None
        self.detection_areas = []
        self.selection_rect = None
        self.selection_start = None
        self.mouse_listener = None

        # 创建主界面
        self.root = tk.Tk()
        self.root.title("石板洗练助手")
        self.root.geometry("900x600")

        # 加载上次的配置
        self.load_config()

        # 主框架 - 左右布局
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左侧控制面板
        left_panel = tk.Frame(main_frame, width=300)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        left_panel.pack_propagate(False)

        # 右侧日志面板
        right_panel = tk.Frame(main_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ===== 左侧控制面板内容 =====
        tk.Label(left_panel, text="石板洗练助手", font=('Arial', 14, 'bold')).pack(pady=10)

        # 1. 洗练按钮设置区域
        wash_frame = tk.LabelFrame(left_panel, text="1. 洗练按钮设置", padx=5, pady=5)
        wash_frame.pack(fill=tk.X, pady=5)

        self.btn_wash = tk.Button(wash_frame, text="选择洗练按钮位置",
                                command=self.select_wash_button,
                                width=20, height=1)
        self.btn_wash.pack(pady=5)

        self.wash_pos_label = tk.Label(wash_frame, text="", fg="gray", wraplength=250)
        self.wash_pos_label.pack()

        # 2. 检测区域设置
        area_frame = tk.LabelFrame(left_panel, text="2. 词条检测区域设置", padx=5, pady=5)
        area_frame.pack(fill=tk.X, pady=5)

        self.btn_area = tk.Button(area_frame, text="添加词条检测区域",
                                command=self.add_detection_area,
                                width=20, height=1)
        self.btn_area.pack(pady=5)

        self.area_count = tk.Label(area_frame, text="当前检测区域: 0/5", font=('Arial', 10))
        self.area_count.pack()

        # 3. 目标设置
        target_frame = tk.LabelFrame(left_panel, text="3. 洗练目标设置", padx=5, pady=5)
        target_frame.pack(fill=tk.X, pady=5)

        tk.Label(target_frame, text="目标红词条数量:").pack(anchor=tk.W)

        # 使用单选按钮组
        self.target_var = tk.IntVar(value=5)
        self.target_radios = []
        radio_frame = tk.Frame(target_frame)
        radio_frame.pack(fill=tk.X, pady=5)

        for i in range(1, 6):
            rb = tk.Radiobutton(radio_frame, text=str(i), variable=self.target_var,
                              value=i, command=self.update_target_setting)
            rb.pack(side=tk.LEFT, padx=5)
            self.target_radios.append(rb)

        # 开始按钮
        self.btn_start = tk.Button(left_panel, text="开始洗练",
                                 command=self.start_washing,
                                 state=tk.DISABLED,
                                 width=20, height=2)
        self.btn_start.pack(pady=15)

        # 状态显示
        self.status = tk.Label(left_panel, text="等待开始操作...", font=('Arial', 10), fg="blue")
        self.status.pack()

        # 自动加载提示
        self.auto_load_label = tk.Label(left_panel, text="", fg="green", wraplength=250)
        self.auto_load_label.pack()

        # ===== 右侧日志面板 =====
        tk.Label(right_panel, text="操作日志", font=('Arial', 12)).pack()

        self.log_area = scrolledtext.ScrolledText(right_panel, width=70, height=30)
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self.log("程序启动，请按顺序进行操作")

        # 运行状态
        self.running = False
        self.paused = False
        self.wash_times = 0
        self.washing_thread = None

        # 设置全局热键
        self.setup_hotkeys()

        # 选择框可视化
        self.selection_canvas = None
        self.selection_window = None

        # 更新自动加载提示
        self.update_auto_load_hint()

    def update_target_setting(self):
        """更新目标设置状态"""
        for rb in self.target_radios:
            rb.config(state=tk.NORMAL if not self.running or self.paused else tk.DISABLED)

    def load_config(self):
        """加载上次的配置"""
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self.wash_button_pos = tuple(config.get('wash_button_pos', ()))
                    self.detection_areas = [tuple(area) for area in config.get('detection_areas', [])]
                    self.target_var.set(config.get('target_red', 5))
            except Exception as e:
                self.wash_button_pos = None
                self.detection_areas = []

    def save_config(self):
        """保存当前配置"""
        config = {
            'wash_button_pos': self.wash_button_pos,
            'detection_areas': self.detection_areas,
            'target_red': self.target_var.get()
        }
        with open(self.CONFIG_FILE, 'w') as f:
            json.dump(config, f)

    def update_auto_load_hint(self):
        """更新自动加载提示"""
        if self.wash_button_pos or self.detection_areas:
            msg = "已自动加载上次的按钮位置和检测区域\n如欲更改请重新点击上方按钮进行操作"
            self.auto_load_label.config(text=msg)

            if self.wash_button_pos:
                self.wash_pos_label.config(text=f"当前按钮位置: {self.wash_button_pos}")

            if self.detection_areas:
                self.area_count.config(text=f"当前检测区域: {len(self.detection_areas)}/5")

            self.check_ready()

    def setup_hotkeys(self):
        """设置全局热键"""
        def on_press(key):
            if key == keyboard.Key.f2:
                self.toggle_pause()

        self.keyboard_listener = keyboard.Listener(on_press=on_press)
        self.keyboard_listener.start()

    def toggle_pause(self):
        """切换暂停状态"""
        if not self.running:
            return

        self.paused = not self.paused
        if self.paused:
            self.status.config(text="已暂停", fg="orange")
            self.log("程序已暂停")
            self.btn_start.config(text="继续洗练", state=tk.NORMAL)
            self.update_target_setting()  # 暂停时启用目标设置
        else:
            self.status.config(text="洗练中...", fg="red")
            self.log("程序已恢复")
            self.btn_start.config(text="暂停请按F2", state=tk.DISABLED)
            self.update_target_setting()  # 恢复时禁用目标设置
            if not self.washing_thread.is_alive():
                self.washing_thread = threading.Thread(
                    target=self._washing_loop,
                    args=(self.target_var.get(),),
                    daemon=True
                )
                self.washing_thread.start()

    def log(self, message):
        """记录日志信息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)
        self.root.update()

    def select_wash_button(self):
        """选择洗练按钮位置"""
        self.log("开始选择洗练按钮位置...")
        self.status.config(text="请将鼠标移动到洗练按钮上，然后按空格键", fg="green")

        temp_window = tk.Toplevel(self.root)
        temp_window.title("请按空格键确认位置")
        temp_window.geometry("300x100+500+300")
        tk.Label(temp_window, text="鼠标移动到洗练按钮上后按空格键确认").pack(pady=20)

        def on_key_press(key):
            try:
                if key == keyboard.Key.space:
                    self.wash_button_pos = pyautogui.position()
                    temp_window.destroy()
                    self.log(f"洗练按钮位置已设置: {self.wash_button_pos}")
                    self.wash_pos_label.config(text=f"当前按钮位置: {self.wash_button_pos}")
                    self.status.config(text=f"洗练按钮位置已设置", fg="blue")
                    self.save_config()
                    self.check_ready()
                    return False
            except:
                pass

        listener = keyboard.Listener(on_press=on_key_press)
        listener.start()

    def add_detection_area(self):
        """添加矩形检测区域"""
        if not self.wash_button_pos:
            messagebox.showwarning("提示", "请先选择洗练按钮位置！")
            return

        self.stop_mouse_listener()

        self.log("开始添加词条检测区域...")
        self.status.config(text="请拖动鼠标框选词条区域(先点击左上角，再拖动到右下角)", fg="green")

        self.create_selection_window()
        self.selection_start = None
        self.selection_rect = None

        threading.Thread(target=self.start_area_selection, daemon=True).start()

    def stop_mouse_listener(self):
        """安全停止鼠标监听器"""
        if hasattr(self, 'mouse_listener') and self.mouse_listener is not None:
            try:
                self.mouse_listener.stop()
            except:
                pass
            self.mouse_listener = None

    def start_area_selection(self):
        """启动区域选择监听"""
        def on_click(x, y, button, pressed):
            if button == mouse.Button.left:
                if pressed:
                    self.selection_start = (x, y)
                    self.selection_rect = None
                else:
                    if self.selection_start is None:
                        return

                    end_pos = (x, y)
                    x1, x2 = sorted([self.selection_start[0], end_pos[0]])
                    y1, y2 = sorted([self.selection_start[1], end_pos[1]])
                    area = (x1, y1, x2, y2)

                    self.root.after(0, lambda: self.finish_area_selection(area))
                    return False

        def on_move(x, y):
            if self.selection_start:
                self.root.after(0, lambda: self.update_selection_rect(self.selection_start, (x, y)))

        self.mouse_listener = mouse.Listener(on_click=on_click, on_move=on_move)
        self.mouse_listener.start()
        self.mouse_listener.join()

    def finish_area_selection(self, area):
        """完成区域选择后的处理"""
        try:
            self.detection_areas.append(area)
            if self.selection_window:
                self.selection_window.destroy()
                self.selection_window = None

            self.log(f"已添加检测区域 {len(self.detection_areas)}: {area}")
            self.area_count.config(text=f"当前检测区域: {len(self.detection_areas)}/5")
            self.status.config(text=f"已添加区域 {len(self.detection_areas)}", fg="blue")
            self.save_config()
            self.check_ready()
        except Exception as e:
            self.log(f"区域选择错误: {str(e)}")

    def create_selection_window(self):
        """创建用于选择区域的透明窗口"""
        if self.selection_window is not None:
            try:
                self.selection_window.destroy()
            except:
                pass

        self.selection_window = tk.Toplevel(self.root)
        self.selection_window.attributes('-fullscreen', True)
        self.selection_window.attributes('-alpha', 0.3)
        self.selection_window.attributes('-topmost', True)

        self.selection_canvas = tk.Canvas(self.selection_window,
                                        cursor="cross",
                                        highlightthickness=0)
        self.selection_canvas.pack(fill=tk.BOTH, expand=True)

    def update_selection_rect(self, start_pos, end_pos):
        """更新选择框可视化"""
        if not self.selection_canvas:
            return

        self.selection_canvas.delete("selection")
        x1, y1 = start_pos
        x2, y2 = end_pos

        self.selection_canvas.create_rectangle(
            x1, y1, x2, y2,
            outline="red", width=2,
            tags="selection"
        )
        self.selection_window.update()

    def check_ready(self):
        """检查是否可以开始洗练"""
        if self.wash_button_pos and len(self.detection_areas) >= 1:
            self.btn_start.config(state=tk.NORMAL)
            self.log("准备就绪，可以开始洗练")

    def start_washing(self):
        """开始洗练流程"""
        if not self.detection_areas:
            messagebox.showwarning("警告", "请至少添加一个检测区域！")
            return

        if self.paused:
            # 恢复暂停状态
            self.paused = False
            self.status.config(text="洗练中...", fg="red")
            self.log("程序已恢复")
            self.btn_start.config(text="暂停请按F2", state=tk.DISABLED)
            self.update_target_setting()
            return

        # 全新开始洗练
        self.running = True
        self.paused = False
        self.wash_times = 0
        self.btn_start.config(text="暂停请按F2", state=tk.DISABLED)
        self.status.config(text="洗练中...", fg="red")
        self.log("=== 开始洗练 ===")

        target_red = self.target_var.get()
        self.log(f"目标: 检测到{target_red}个红色词条时停止")

        self.washing_thread = threading.Thread(
            target=self._washing_loop,
            args=(target_red,),
            daemon=True
        )
        self.washing_thread.start()

    def _washing_loop(self, initial_target):
        """洗练循环的实际工作函数"""
        try:
            current_target = initial_target
            while self.running:
                if self.paused:
                    # 暂停时检查是否有目标值变更
                    new_target = self.target_var.get()
                    if new_target != current_target:
                        self.log(f"目标红词条数量已变更: {current_target} → {new_target}")
                        current_target = new_target
                    time.sleep(0.5)
                    continue

                self.wash_times += 1
                self.root.after(0, lambda: pyautogui.click(self.wash_button_pos))
                self.root.after(0, lambda: self.log(f"第{self.wash_times}次洗练: 点击洗练按钮"))

                time.sleep(0.5)

                red_count = 0
                area_results = []

                for i, area in enumerate(self.detection_areas, 1):
                    screenshot = ImageGrab.grab(bbox=area)
                    pixels = np.array(screenshot)

                    red_mask = (
                        (pixels[:,:,0] > self.RED_COLOR[0] - self.COLOR_TOLERANCE) &
                        (pixels[:,:,0] < self.RED_COLOR[0] + self.COLOR_TOLERANCE) &
                        (pixels[:,:,1] > self.RED_COLOR[1] - self.COLOR_TOLERANCE) &
                        (pixels[:,:,1] < self.RED_COLOR[1] + self.COLOR_TOLERANCE) &
                        (pixels[:,:,2] > self.RED_COLOR[2] - self.COLOR_TOLERANCE) &
                        (pixels[:,:,2] < self.RED_COLOR[2] + self.COLOR_TOLERANCE)
                    )

                    red_pixels = np.sum(red_mask)
                    is_red = red_pixels >= 10
                    red_count += int(is_red)
                    area_results.append(f"区域{i}:{'红' if is_red else '非红'}")

                result_log = " | ".join(area_results)
                self.root.after(0, lambda: self.log(f"检测结果: {result_log} (总计红色: {red_count})"))

                if red_count >= current_target:
                    self.root.after(0, lambda: self._complete_washing(red_count))
                    break

                time.sleep(0.3)

        except Exception as e:
            self.root.after(0, lambda: self._handle_error(e))

    def _complete_washing(self, red_count):
        """完成洗练后的处理"""
        winsound.Beep(1000, 1000)
        self.log(f"★ 达到目标! 检测到{red_count}个红色词条 ★")
        self.status.config(text=f"达到目标! {red_count}个红色词条", fg="green")
        self.running = False
        self.paused = False
        self.btn_start.config(text="开始洗练", state=tk.NORMAL)
        self.update_target_setting()

    def _handle_error(self, error):
        """错误处理"""
        self.log(f"错误: {str(error)}")
        messagebox.showerror("错误", f"程序运行出错: {str(error)}")
        self.running = False
        self.paused = False
        self.btn_start.config(text="开始洗练", state=tk.NORMAL)
        self.update_target_setting()

if __name__ == "__main__":
    try:
        app = StoneWashHelper()
        app.root.mainloop()
    except Exception as e:
        with open("error.log", "a") as f:
            f.write(f"{datetime.now()} CRASH: {str(e)}\n")
        messagebox.showerror("致命错误", f"程序崩溃: {str(e)}")