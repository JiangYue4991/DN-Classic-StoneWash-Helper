import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import json
import os
import threading
import time
from datetime import datetime
import pyautogui
from PIL import ImageGrab, Image
import numpy as np
import winsound
from pynput import keyboard, mouse
import sys
import gc


class StoneWashingAssistant:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("石板洗练助手 v3.0")
        self.root.geometry("1000x820")
        self.root.resizable(True, True)

        # 设置程序图标（如果有的话）
        try:
            if os.path.exists("icon.ico"):
                self.root.iconbitmap("icon.ico")
        except:
            pass

        # 配置变量
        self.config_file = "config.json"
        self.wash_button_pos = None
        self.detection_areas = [None] * 6
        self.use_advanced_strategy = False
        self.area_color_requirements = ["无"] * 6
        self.min_red_count = 1

        # 状态变量
        self.is_running = False
        self.is_paused = False
        self.current_state = "等待开始操作..."
        self.log_lock = threading.Lock()

        # 洗练计数器 - 改为全局累加，不再重置
        self.wash_count = 0

        # 监听器
        self.key_listener = None
        self.mouse_listener = None
        self.selecting_area = False
        self.selection_start = None
        self.selection_window = None
        self.current_area_index = None

        # 热键注册
        self.hotkey_listener = None

        # 选择按钮提示窗口
        self.selection_prompt_window = None

        # 图像处理缓存
        self.image_cache = {}
        self.cache_timeout = 5  # 缓存超时时间（秒）

        # 性能监控
        self.performance_stats = {
            "screenshot_time": 0,
            "analysis_time": 0,
            "total_cycles": 0
        }

        # 初始化GUI
        self.setup_ui()

        # 加载配置
        self.load_config()

        # 延迟启动热键监听，避免PyCharm兼容性问题
        self.root.after(1000, self.start_hotkey_listener)

        # 设置内存清理定时器
        self.root.after(60000, self.cleanup_memory)

    def setup_ui(self):
        """设置用户界面"""
        # 左侧控制面板
        control_frame = tk.Frame(self.root, bg="#f0f0f0")
        control_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)

        # 创建一个容器Frame用于固定左侧面板宽度
        left_container = tk.Frame(control_frame, width=380, bg="#f0f0f0")
        left_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
        left_container.pack_propagate(False)

        # 创建Canvas和滚动条，使左侧面板可滚动
        canvas = tk.Canvas(left_container, bg="#f0f0f0", highlightthickness=0)
        scrollbar = tk.Scrollbar(left_container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#f0f0f0", width=360)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=360)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 保存canvas和scrollable_frame的引用
        self.left_canvas = canvas
        self.scrollable_frame = scrollable_frame

        # 标题
        title_label = tk.Label(scrollable_frame, text="石板洗练助手 v3.0",
                               font=("微软雅黑", 16, "bold"), bg="#f0f0f0")
        title_label.pack(pady=10)

        # 洗练按钮设置区域
        wash_frame = tk.LabelFrame(scrollable_frame, text="洗练按钮设置",
                                   font=("微软雅黑", 10), bg="#f0f0f0")
        wash_frame.pack(padx=10, pady=3, fill=tk.X)

        tk.Button(wash_frame, text="选择洗练按钮位置",
                  command=self.select_wash_button,
                  font=("微软雅黑", 9)).pack(padx=10, pady=3)

        self.wash_pos_label = tk.Label(wash_frame, text="未设置",
                                       font=("微软雅黑", 9), bg="#f0f0f0")
        self.wash_pos_label.pack(pady=3)

        # 检测区域管理
        detect_frame = tk.LabelFrame(scrollable_frame, text="检测区域管理 (最多6个)",
                                     font=("微软雅黑", 10), bg="#f0f0f0")
        detect_frame.pack(padx=10, pady=5, fill=tk.X)

        # 创建6个检测区域控件
        self.area_buttons = []
        self.area_status_labels = []

        for i in range(6):
            area_frame = tk.Frame(detect_frame, bg="#f0f0f0")
            area_frame.pack(padx=5, pady=2, fill=tk.X)

            capture_btn = tk.Button(area_frame, text=f"📷 区域{i + 1}", width=10,
                                    command=lambda idx=i: self.capture_area(idx),
                                    font=("微软雅黑", 9))
            capture_btn.pack(side=tk.LEFT, padx=5)

            status_label = tk.Label(area_frame, text="未设置",
                                    font=("微软雅黑", 9), bg="#f0f0f0", fg="red")
            status_label.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

            self.area_buttons.append(capture_btn)
            self.area_status_labels.append(status_label)

        # 全局区域操作按钮
        global_frame = tk.Frame(detect_frame, bg="#f0f0f0")
        global_frame.pack(padx=5, pady=5, fill=tk.X)

        tk.Button(global_frame, text="重置所有区域",
                  command=self.reset_all_areas,
                  font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=5, expand=True)

        tk.Button(global_frame, text="测试所有区域",
                  command=self.test_all_areas,
                  font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=5, expand=True)

        # 洗练策略设置
        strategy_frame = tk.LabelFrame(scrollable_frame, text="洗练目标策略",
                                       font=("微软雅黑", 10), bg="#f0f0f0")
        strategy_frame.pack(padx=10, pady=5, fill=tk.X)

        # 基础模式
        base_frame = tk.Frame(strategy_frame, bg="#f0f0f0")
        base_frame.pack(padx=10, pady=3, fill=tk.X)

        tk.Label(base_frame, text="最低红色词条数量:",
                 font=("微软雅黑", 9), bg="#f0f0f0").pack(side=tk.LEFT)

        self.min_red_var = tk.StringVar(value="1")
        min_red_combo = ttk.Combobox(base_frame, textvariable=self.min_red_var,
                                     values=[str(i) for i in range(1, 7)],
                                     width=5, state="readonly")
        min_red_combo.pack(side=tk.LEFT, padx=5)
        min_red_combo.bind("<<ComboboxSelected>>", self.save_config)

        # 高级策略开关
        self.advanced_var = tk.BooleanVar(value=False)
        advanced_check = tk.Checkbutton(strategy_frame, text="启用高级洗练目标策略",
                                        variable=self.advanced_var,
                                        command=self.toggle_advanced_strategy,
                                        font=("微软雅黑", 9), bg="#f0f0f0")
        advanced_check.pack(anchor="w", padx=10, pady=(0, 3))

        # 高级策略区域（初始隐藏）
        self.advanced_frame = tk.Frame(strategy_frame, bg="#f0f0f0")

        tk.Label(self.advanced_frame, text="各区域颜色需求:",
                 font=("微软雅黑", 9), bg="#f0f0f0").pack(anchor="w", padx=10, pady=(3, 3))

        # 创建6个区域的颜色需求下拉框
        self.color_vars = []
        color_frame = tk.Frame(self.advanced_frame, bg="#f0f0f0")
        color_frame.pack(padx=10, pady=3)

        for i in range(6):
            frame = tk.Frame(color_frame, bg="#f0f0f0")
            frame.grid(row=i // 2, column=i % 2, padx=5, pady=2)

            tk.Label(frame, text=f"区域{i + 1}:",
                     font=("微软雅黑", 8), bg="#f0f0f0").pack(side=tk.LEFT)

            color_var = tk.StringVar(value="无")
            color_combo = ttk.Combobox(frame, textvariable=color_var,
                                       values=["无", "红"],
                                       width=10, state="readonly", font=("微软雅黑", 8))
            color_combo.pack(side=tk.LEFT, padx=2)
            color_combo.bind("<<ComboboxSelected>>", self.save_config)

            self.color_vars.append(color_var)

        # 执行控制
        execute_frame = tk.LabelFrame(scrollable_frame, text="执行控制",
                                      font=("微软雅黑", 10), bg="#f0f0f0")
        execute_frame.pack(padx=10, pady=10, fill=tk.X)

        self.start_btn = tk.Button(execute_frame, text="开始洗练",
                                   command=self.toggle_washing,
                                   font=("微软雅黑", 10), bg="#4CAF50", fg="white",
                                   width=15, height=2)
        self.start_btn.pack(pady=8)

        tk.Label(execute_frame, text="热键: F2 暂停/继续",
                 font=("微软雅黑", 8), bg="#f0f0f0", fg="#666").pack()

        # 性能统计显示
        self.stats_label = tk.Label(execute_frame, text="",
                                    font=("微软雅黑", 8), bg="#f0f0f0", fg="#666")
        self.stats_label.pack(pady=3)

        # 修复：只在内容超出时启用滚动，并正确绑定鼠标滚轮事件
        def on_mousewheel(event):
            # 获取scrollable_frame和canvas的实际尺寸
            frame_height = scrollable_frame.winfo_reqheight()
            canvas_height = canvas.winfo_height()

            # 只有当scrollable_frame的高度大于canvas的高度时才允许滚动
            if frame_height > canvas_height:
                # 计算滚动步数（Windows鼠标滚轮事件delta通常是120的倍数）
                scroll_step = -1 * (event.delta // 120)
                canvas.yview_scroll(scroll_step, "units")

        # 绑定鼠标滚轮事件到canvas
        canvas.bind("<MouseWheel>", on_mousewheel)

        # 同时绑定到scrollable_frame内的所有控件，确保鼠标在内容区域也能滚动
        def bind_mousewheel_to_children(widget):
            widget.bind("<MouseWheel>", on_mousewheel)
            for child in widget.winfo_children():
                bind_mousewheel_to_children(child)

        bind_mousewheel_to_children(scrollable_frame)

        # 右侧主区域
        right_frame = tk.Frame(self.root)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 状态栏（移到右侧）
        self.status_label = tk.Label(right_frame, text=self.current_state,
                                     font=("微软雅黑", 9), bg="#e0e0e0",
                                     relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.TOP, fill=tk.X, pady=(0, 5), ipady=5)

        # 日志区域
        log_frame = tk.Frame(right_frame)
        log_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        tk.Label(log_frame, text="执行日志",
                 font=("微软雅黑", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD,
                                                  font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 初始日志
        self.log_message("石板洗练助手 v3.0 已启动")

    def toggle_advanced_strategy(self):
        """切换高级策略显示"""
        if self.advanced_var.get():
            self.advanced_frame.pack(padx=10, pady=3, fill=tk.X)
            for i, var in enumerate(self.color_vars):
                var.set(self.area_color_requirements[i])
        else:
            self.advanced_frame.pack_forget()

        self.use_advanced_strategy = self.advanced_var.get()
        self.save_config()

    def select_wash_button(self):
        """选择洗练按钮位置"""
        if self.key_listener:
            self.key_listener.stop()
            self.key_listener = None

        if self.selection_prompt_window:
            try:
                self.selection_prompt_window.destroy()
            except:
                pass
            self.selection_prompt_window = None

        self.log_message("请将鼠标移至洗练按钮上，按空格键确认")
        self.current_state = "请将鼠标移至洗练按钮上，按空格键确认"
        self.update_status()

        self.create_selection_prompt_window()

        self.key_listener = keyboard.Listener(on_press=self.on_space_press)
        self.key_listener.start()

    def create_selection_prompt_window(self):
        """创建选择洗练按钮位置的提示窗口"""
        self.selection_prompt_window = tk.Toplevel(self.root)
        self.selection_prompt_window.title("提示")
        self.selection_prompt_window.geometry("300x150")
        self.selection_prompt_window.resizable(False, False)
        self.selection_prompt_window.attributes('-topmost', True)

        # 居中显示
        self.selection_prompt_window.transient(self.root)
        self.selection_prompt_window.grab_set()

        label = tk.Label(self.selection_prompt_window,
                         text="请将鼠标移至洗练按钮上\n按空格键确认",
                         font=("微软雅黑", 12))
        label.pack(pady=20)

        cancel_btn = tk.Button(self.selection_prompt_window, text="取消",
                               command=self.cancel_wash_button_selection,
                               font=("微软雅黑", 10), width=10)
        cancel_btn.pack(pady=10)

    def cancel_wash_button_selection(self):
        """取消洗练按钮选择"""
        if self.key_listener:
            self.key_listener.stop()
            self.key_listener = None

        if self.selection_prompt_window:
            self.selection_prompt_window.destroy()
            self.selection_prompt_window = None

        self.log_message("已取消选择洗练按钮位置")
        self.current_state = "等待开始操作..."
        self.update_status()

    def on_space_press(self, key):
        """空格键按下时的处理"""
        try:
            if key == keyboard.Key.space:
                if self.key_listener:
                    self.key_listener.stop()
                    self.key_listener = None

                self.wash_button_pos = pyautogui.position()

                if self.selection_prompt_window:
                    self.selection_prompt_window.destroy()
                    self.selection_prompt_window = None

                self.wash_pos_label.config(text="✓ 已设置", fg="green")
                self.log_message(f"洗练按钮位置已设置")
                self.current_state = "洗练按钮位置已设置"
                self.update_status()
                self.save_config()

        except Exception as e:
            self.log_message(f"获取位置失败: {str(e)}", "ERROR")

    def capture_area(self, area_index):
        """捕获检测区域"""
        self.current_area_index = area_index
        self.selecting_area = True

        self.selection_window = tk.Toplevel(self.root)
        self.selection_window.attributes('-fullscreen', True)
        self.selection_window.attributes('-alpha', 0.3)
        self.selection_window.attributes('-topmost', True)

        canvas = tk.Canvas(self.selection_window, highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)

        self.selection_start = None
        self.selection_rect = None

        def on_mouse_down(event):
            self.selection_start = (event.x, event.y)

        def on_mouse_move(event):
            if self.selection_start:
                if self.selection_rect:
                    canvas.delete(self.selection_rect)
                self.selection_rect = canvas.create_rectangle(
                    self.selection_start[0], self.selection_start[1],
                    event.x, event.y,
                    outline='red', width=2
                )

        def on_mouse_up(event):
            if self.selection_start:
                x1, y1 = self.selection_start
                x2, y2 = event.x, event.y

                x1, x2 = min(x1, x2), max(x1, x2)
                y1, y2 = min(y1, y2), max(y1, y2)

                self.detection_areas[area_index] = (x1, y1, x2, y2)
                self.update_area_ui(area_index)

                self.selection_window.destroy()
                self.selecting_area = False
                self.selection_start = None

                self.log_message(f"区域{area_index + 1}已设置")
                self.save_config()

        canvas.bind("<Button-1>", on_mouse_down)
        canvas.bind("<B1-Motion>", on_mouse_move)
        canvas.bind("<ButtonRelease-1>", on_mouse_up)

        def on_escape(event):
            self.selection_window.destroy()
            self.selecting_area = False
            self.log_message("区域选择已取消")

        self.selection_window.bind("<Escape>", on_escape)

    def update_area_ui(self, area_index):
        """更新区域UI状态"""
        area = self.detection_areas[area_index]
        if area:
            self.area_status_labels[area_index].config(text="✓ 已设置", fg="green")
        else:
            self.area_status_labels[area_index].config(text="未设置", fg="red")

    def reset_all_areas(self):
        """重置所有检测区域"""
        for i in range(6):
            self.detection_areas[i] = None
            self.update_area_ui(i)

        self.log_message("所有区域已重置")
        self.save_config()

    def test_all_areas(self):
        """测试所有检测区域"""
        for i in range(6):
            area = self.detection_areas[i]
            if not area:
                continue

            try:
                screenshot = ImageGrab.grab(bbox=area)
                is_red = self.is_red_area(screenshot)
                result = "红" if is_red else "非红"
                self.log_message(f"区域{i + 1}测试 → {result}")
            except Exception as e:
                self.log_message(f"区域{i + 1}测试失败: {str(e)}", "ERROR")

    def is_red_area(self, image):
        """判断区域是否为红色"""
        # 目标RGB和容差
        target_r, target_g, target_b = (220, 35, 85)
        tolerance = 30

        # 转换为numpy数组并预计算掩码
        img_array = np.array(image)

        # 使用向量化操作，提高性能
        red_mask = (
                (img_array[:, :, 0] >= target_r - tolerance) &
                (img_array[:, :, 0] <= target_r + tolerance) &
                (img_array[:, :, 1] >= target_g - tolerance) &
                (img_array[:, :, 1] <= target_g + tolerance) &
                (img_array[:, :, 2] >= target_b - tolerance) &
                (img_array[:, :, 2] <= target_b + tolerance)
        )

        red_pixel_count = np.sum(red_mask)

        return red_pixel_count >= 10

    def is_any_color_area(self, image):
        """判断区域是否有任意颜色（非空白）"""
        # 转换为灰度图
        gray_image = image.convert('L')
        gray_array = np.array(gray_image)

        # 计算非背景像素
        non_bg_pixels = np.sum(gray_array < 240)

        return non_bg_pixels > 50

    def toggle_washing(self):
        """切换洗练状态"""
        if not self.is_running:
            if not self.wash_button_pos:
                messagebox.showerror("错误", "请先设置洗练按钮位置")
                return

            if not any(self.detection_areas):
                messagebox.showerror("错误", "请至少设置一个检测区域")
                return

            self.is_running = True
            self.is_paused = False
            self.start_btn.config(text="暂停", bg="#FF9800")
            self.current_state = "洗练中..."
            self.update_status()

            # 注意：这里不再重置洗练计数器，保持累加

            self.washing_thread = threading.Thread(target=self.washing_loop, daemon=True)
            self.washing_thread.start()

            self.log_message("开始洗练...")

        elif not self.is_paused:
            self.is_paused = True
            self.start_btn.config(text="继续", bg="#4CAF50")
            self.current_state = "已暂停"
            self.update_status()
            self.log_message("洗练已暂停")
        else:
            self.is_paused = False
            self.start_btn.config(text="暂停", bg="#FF9800")
            self.current_state = "洗练中..."
            self.update_status()
            self.log_message("洗练继续")

    def washing_loop(self):
        """洗练主循环"""
        consecutive_failures = 0
        last_performance_update = time.time()

        while self.is_running:
            if self.is_paused:
                time.sleep(0.1)
                continue

            try:
                start_time = time.time()

                if self.wash_button_pos:
                    self.wash_count += 1  # 计数器累加
                    pyautogui.click(self.wash_button_pos)
                    self.log_message(f"第{self.wash_count}次洗练")
                else:
                    self.log_message("洗练按钮位置未设置", "ERROR")
                    break

                # 等待动画完成
                self.wait_for_animation_complete()

                # 分析所有区域
                red_count = 0
                area_results = []

                for i, area in enumerate(self.detection_areas):
                    if not area:
                        area_results.append(None)
                        continue

                    try:
                        # 截图并分析
                        screenshot_start = time.time()
                        screenshot = ImageGrab.grab(bbox=area)
                        self.performance_stats["screenshot_time"] += time.time() - screenshot_start

                        analysis_start = time.time()
                        is_red = self.is_red_area(screenshot)
                        has_content = self.is_any_color_area(screenshot)
                        self.performance_stats["analysis_time"] += time.time() - analysis_start

                        area_results.append({
                            'red': is_red,
                            'has_content': has_content
                        })

                        if is_red:
                            red_count += 1

                    except Exception as e:
                        area_results.append(None)
                        self.log_message(f"区域{i + 1}分析失败: {str(e)}", "ERROR")

                self.performance_stats["total_cycles"] += 1

                # 更新性能统计显示（每10次循环更新一次）
                current_time = time.time()
                if current_time - last_performance_update > 5:
                    avg_screenshot = self.performance_stats["screenshot_time"] / self.performance_stats[
                        "total_cycles"] if self.performance_stats["total_cycles"] > 0 else 0
                    avg_analysis = self.performance_stats["analysis_time"] / self.performance_stats["total_cycles"] if \
                        self.performance_stats["total_cycles"] > 0 else 0

                    stats_text = f"性能: 截图{avg_screenshot:.3f}s/次, 分析{avg_analysis:.3f}s/次"
                    self.root.after(0, lambda: self.stats_label.config(text=stats_text))
                    last_performance_update = current_time

                # 记录结果
                self.log_message(f"检测到 {red_count} 个红色词条")

                # 实时获取当前设置的目标条件
                current_min_red_count = int(self.min_red_var.get())
                current_use_advanced_strategy = self.advanced_var.get()

                # 修复：在检查终止条件之前获取当前的颜色需求设置
                current_area_color_requirements = []
                if current_use_advanced_strategy:
                    current_area_color_requirements = [var.get() for var in self.color_vars]
                else:
                    current_area_color_requirements = ["无"] * 6

                # 检查终止条件
                if self.check_termination_condition(red_count, area_results,
                                                    current_min_red_count,
                                                    current_use_advanced_strategy,
                                                    current_area_color_requirements):
                    self.log_message(f"达到目标! 共 {red_count} 个红色词条 (第{self.wash_count}次洗练)", "SUCCESS")

                    try:
                        winsound.Beep(1000, 1000)
                    except:
                        pass

                    self.root.after(0, lambda: messagebox.showinfo(
                        "洗练完成",
                        f"已达到洗练目标!\n第{self.wash_count}次洗练，共检测到 {red_count} 个红色词条"
                    ))

                    self.is_running = False
                    self.root.after(0, self.reset_ui_state)
                    break

                consecutive_failures = 0

            except Exception as e:
                self.log_message(f"洗练循环出错: {str(e)}", "ERROR")
                consecutive_failures += 1

                if consecutive_failures >= 3:
                    self.log_message("连续失败3次，停止洗练", "ERROR")
                    self.is_running = False
                    self.root.after(0, self.reset_ui_state)
                    break

            # 根据性能动态调整延迟
            cycle_time = time.time() - start_time
            if cycle_time < 0.3:
                time.sleep(0.3 - cycle_time)
            else:
                time.sleep(0.1)

    def check_termination_condition(self, red_count, area_results,
                                    min_red_count, use_advanced_strategy, area_color_requirements):
        """检查终止条件"""
        if not use_advanced_strategy:
            return red_count >= min_red_count

        # 高级策略检查
        for i in range(6):
            req = area_color_requirements[i]
            if req == "无":
                continue

            if i >= len(area_results) or area_results[i] is None:
                return False

            if req == "红" and not area_results[i]['red']:
                return False

        return red_count >= min_red_count

    def wait_for_animation_complete(self, timeout=5):
        """等待动画完成（基于灰度变化检测）"""
        reference_area = None
        for area in self.detection_areas:
            if area:
                reference_area = area
                break

        if not reference_area:
            time.sleep(0.5)
            return

        # 优化：减少采样次数
        prev_gray = None
        stable_count = 0
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                screenshot = ImageGrab.grab(bbox=reference_area)
                gray_img = screenshot.convert('L')
                current_gray = np.mean(np.array(gray_img))

                if prev_gray is None:
                    prev_gray = current_gray
                elif abs(current_gray - prev_gray) < 5:
                    stable_count += 1
                    if stable_count >= 2:
                        break
                else:
                    stable_count = 0

                prev_gray = current_gray
                time.sleep(0.08)

            except Exception:
                time.sleep(0.08)
                continue

    def reset_ui_state(self):
        """重置UI状态"""
        self.is_running = False
        self.is_paused = False
        self.start_btn.config(text="开始洗练", bg="#4CAF50")
        self.current_state = "等待开始操作..."
        self.update_status()

    def start_hotkey_listener(self):
        """启动热键监听器"""

        def on_f2_press(key):
            if key == keyboard.Key.f2 and self.is_running:
                self.root.after(0, self.toggle_washing)

        self.hotkey_listener = keyboard.Listener(on_press=on_f2_press)
        self.hotkey_listener.start()

    def cleanup_memory(self):
        """清理内存"""
        try:
            # 清理过期的图像缓存
            current_time = time.time()
            expired_keys = []
            for key, (timestamp, _) in list(self.image_cache.items()):
                if current_time - timestamp > self.cache_timeout:
                    expired_keys.append(key)

            for key in expired_keys:
                del self.image_cache[key]

            # 强制垃圾回收
            gc.collect()

            # 重新设置定时器
            self.root.after(60000, self.cleanup_memory)

        except Exception as e:
            print(f"内存清理出错: {e}")

    def log_message(self, message, level="INFO"):
        """记录日志消息"""
        timestamp = datetime.now().strftime("[%H:%M:%S]")

        if level == "ERROR":
            color = "red"
            prefix = "[错误] "
        elif level == "SUCCESS":
            color = "green"
            prefix = "[成功] "
        else:
            color = "black"
            prefix = ""

        full_message = f"{timestamp} {prefix}{message}"

        with self.log_lock:
            self.log_text.insert(tk.END, full_message + "\n")
            self.log_text.tag_add(color, f"end-{len(full_message) + 2}c", "end-1c")
            self.log_text.tag_config(color, foreground=color)
            self.log_text.see(tk.END)

        if level == "INFO" and not message.startswith("区域"):
            self.current_state = message
            self.update_status()

    def update_status(self):
        """更新状态栏"""
        self.status_label.config(text=f"状态: {self.current_state}")

    def save_config(self, event=None):
        """保存配置到文件"""
        try:
            # 更新当前设置到实例变量
            self.min_red_count = int(self.min_red_var.get())
            self.use_advanced_strategy = self.advanced_var.get()
            if self.use_advanced_strategy:
                self.area_color_requirements = [var.get() for var in self.color_vars]
            else:
                self.area_color_requirements = ["无"] * 6

            config = {
                "wash_button_pos": list(self.wash_button_pos) if self.wash_button_pos else None,
                "detection_areas": [list(area) if area else None for area in self.detection_areas],
                "use_advanced_strategy": self.use_advanced_strategy,
                "area_color_requirements": self.area_color_requirements,
                "min_red_count": self.min_red_count,
                "wash_count": self.wash_count  # 保存洗练计数器
            }

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

        except Exception as e:
            self.log_message(f"保存配置失败: {str(e)}", "ERROR")

    def load_config(self):
        """从文件加载配置"""
        if not os.path.exists(self.config_file):
            self.log_message("未找到配置文件，使用默认配置")
            return

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)

            if config.get("wash_button_pos"):
                self.wash_button_pos = tuple(config["wash_button_pos"])
                self.wash_pos_label.config(text="✓ 已设置", fg="green")

            if config.get("detection_areas"):
                for i, area in enumerate(config["detection_areas"]):
                    if area and len(area) == 4:
                        self.detection_areas[i] = tuple(area)
                        self.update_area_ui(i)

            if config.get("use_advanced_strategy") is not None:
                self.use_advanced_strategy = config["use_advanced_strategy"]
                self.advanced_var.set(self.use_advanced_strategy)

            if config.get("area_color_requirements"):
                self.area_color_requirements = config["area_color_requirements"]
                for i in range(len(self.area_color_requirements)):
                    if self.area_color_requirements[i] == "任意颜色":
                        self.area_color_requirements[i] = "无"

            if config.get("min_red_count"):
                self.min_red_count = config["min_red_count"]
                self.min_red_var.set(str(self.min_red_count))

            # 加载洗练计数器
            if config.get("wash_count"):
                self.wash_count = config["wash_count"]

            if self.use_advanced_strategy:
                self.advanced_frame.pack(padx=10, pady=3, fill=tk.X)
                for i, var in enumerate(self.color_vars):
                    if i < len(self.area_color_requirements):
                        var.set(self.area_color_requirements[i])

            self.log_message(f"已自动加载上次配置，累计洗练次数: {self.wash_count}")

        except Exception as e:
            self.log_message(f"加载配置失败: {str(e)}", "ERROR")

    def on_closing(self):
        """程序关闭时的清理工作"""
        if self.is_running:
            self.is_running = False

        if self.key_listener:
            self.key_listener.stop()
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.hotkey_listener:
            self.hotkey_listener.stop()

        if self.selection_prompt_window:
            try:
                self.selection_prompt_window.destroy()
            except:
                pass

        self.save_config()
        self.root.destroy()

    def run(self):
        """运行主程序"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()


def main():
    """主函数"""
    if sys.platform != "win32":
        print("错误：本程序仅支持Windows系统")
        return

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1

    try:
        app = StoneWashingAssistant()
        app.run()
    except Exception as e:
        with open("error.log", "w", encoding="utf-8") as f:
            f.write(f"{datetime.now()}\n")
            f.write(f"程序崩溃: {str(e)}\n")
            import traceback
            traceback.print_exc(file=f)

        messagebox.showerror("程序错误", f"程序发生错误，详情请查看error.log文件\n\n{str(e)}")


if __name__ == "__main__":
    main()