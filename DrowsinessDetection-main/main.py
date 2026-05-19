import sys
import time
import math
import cv2
import mediapipe as mp
import os # Tambahan untuk mengecek path file mp3
from PyQt5 import QtWidgets, uic, QtCore, QtGui
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent  # Library Audio Resmi untuk MP3

# ==========================================
# INDEKS LANDMARK WAJAH SECARA MANUAL
# ==========================================
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
MOUTH_OUTER = [61, 37, 0, 267, 291, 321, 14, 91] # Titik representatif keliling bibir
NOSE_BRIDGE = [168, 6, 197, 195, 5]             # Garis tengah hidung
EYEBROWS = [70, 63, 105, 66, 296, 334, 293, 300] # Alis kiri & kanan
JAW_LINE = [172, 58, 132, 93, 148, 152, 377, 400, 378, 379, 288, 397] # Dagu/Rahang

class DrowsinessDetectionSystem(QtWidgets.QMainWindow):
    def __init__(self):
        super(DrowsinessDetectionSystem, self).__init__()
        
        # Memuat UI hasil ekspor Qt Designer
        uic.loadUi('ui_main.ui', self)
        
        # Inisialisasi Parameter Citra & Deteksi
        self.EAR_THRESHOLD = 0.18
        self.MAR_THRESHOLD = 0.60
        self.CONSEC_FRAMES = 30  # Berapa frame mata terpejam sebelum alarm bunyi
        
        self.blink_counter = 0
        self.is_running = False
        
        # Pengukur Kinerja (PCD Metric)
        self.fps = 0
        self.frame_count = 0
        self.last_fps_time = time.time()
        
        # Inisialisasi MediaPipe Core
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6
        )
        
        # Inisialisasi Object Player Audio untuk MP3
        self.player = QMediaPlayer()
        # Mengambil lokasi file alarm.mp3 secara absolut biar aman di Windows
        mp3_path = os.path.join(os.getcwd(), "alarm.mp3")
        url = QtCore.QUrl.fromLocalFile(mp3_path)
        self.audio_content = QMediaContent(url)
        self.player.setMedia(self.audio_content)
        
        # Timer Pembacaan Kamera (Thread GUI)
        self.camera_timer = QtCore.QTimer()
        self.camera_timer.timeout.connect(self.process_image_frame)
        
        # Mapping Event Tombol dan Slider di QT Designer
        self.btnStart.clicked.connect(self.action_start)
        self.btnStop.clicked.connect(self.action_stop)
        self.btnTestAlarm.clicked.connect(self.trigger_sys_sound)
        
        self.earThresholdInput.valueChanged.connect(self.sync_parameters)
        self.marThresholdInput.valueChanged.connect(self.sync_parameters)
        
        # Tampilan Awal UI StyleSheet
        self.apply_initial_stylesheet()
        
        # Pastikan tombol Stop mati di awal aplikasi dijalankan
        self.btnStop.setEnabled(False)

    def apply_initial_stylesheet(self):
        self.statusBadge.setText("STATUS: IDLE")
        self.statusBadge.setStyleSheet("""
            background-color: #6b7280; 
            color: #ffffff; 
            font-size: 14px; 
            font-weight: bold; 
            border-radius: 8px;
            padding: 10px;
        """)
        self.FaceDetected.setText("No")
        self.earValue.setText("0.000")
        self.marValue.setText("0.000")
        self.drowsyCounter.setText("0")
        self.fpsCounter.setText("0")

    def sync_parameters(self):
        # Konversi nilai Slider Integer QT ke nilai Float Matematika Citra
        self.EAR_THRESHOLD = self.earThresholdInput.value() / 100.0
        self.MAR_THRESHOLD = self.marThresholdInput.value() / 100.0
        
        self.earThresholdValue.setText(f"{self.EAR_THRESHOLD:.2f}")
        self.marThresholdValue.setText(f"{self.MAR_THRESHOLD:.2f}")

    # ==========================================
    # LOGIKA MATEMATIKA CITRA (PROSES MANUAL)
    # ==========================================
    def calculate_euclidean_distance(self, pt1, pt2):
        return math.sqrt((pt1[0] - pt2[0])**2 + (pt1[1] - pt2[1])**2)

    def extract_eye_aspect_ratio(self, landmarks, indices, width, height):
        pts = [(int(landmarks[idx].x * width), int(landmarks[idx].y * height)) for idx in indices]
        vertical_1 = self.calculate_euclidean_distance(pts[1], pts[5])
        vertical_2 = self.calculate_euclidean_distance(pts[2], pts[4])
        horizontal = self.calculate_euclidean_distance(pts[0], pts[3])
        
        # Pencegahan pembagian dengan nol (zero division error)
        if horizontal == 0:
            return 0.0, pts
            
        ear_score = (vertical_1 + vertical_2) / (2.0 * horizontal)
        return ear_score, pts

    def extract_mouth_aspect_ratio(self, landmarks, indices, width, height):
        pts = [(int(landmarks[idx].x * width), int(landmarks[idx].y * height)) for idx in indices]
        v1 = self.calculate_euclidean_distance(pts[1], pts[7])
        v2 = self.calculate_euclidean_distance(pts[2], pts[6])
        v3 = self.calculate_euclidean_distance(pts[3], pts[5])
        h  = self.calculate_euclidean_distance(pts[0], pts[4])
        
        if h == 0:
            return 0.0, pts
            
        mar_score = (v1 + v2 + v3) / (3.0 * h)
        return mar_score, pts

    def trigger_sys_sound(self):
        # Membunyikan suara secara asinkronus agar GUI tidak macet ketika tombol test diklik
        QtCore.QMetaObject.invokeMethod(self, "play_beep_sound", QtCore.Qt.QueuedConnection)

    @QtCore.pyqtSlot()
    def play_beep_sound(self):
        # Memainkan alarm MP3 sekali putar (untuk testing tombol)
        if self.player.state() != QMediaPlayer.PlayingState:
            self.player.play()

    def action_start(self):
        if not self.is_running:
            self.capture = cv2.VideoCapture(1)
            if self.capture.isOpened():
                self.is_running = True
                self.camera_timer.start(33) # Set interval ~30 FPS
                self.btnStart.setEnabled(False)
                self.btnStop.setEnabled(True)

    def action_stop(self):
        if self.is_running:
            self.is_running = False
            self.camera_timer.stop()
            self.capture.release()
            self.videoLabel.clear()
            self.btnStart.setEnabled(True)
            self.btnStop.setEnabled(False)
            self.blink_counter = 0
            self.player.stop() # Matikan alarm MP3 saat sistem stop
            self.apply_initial_stylesheet()

    # ==========================================
    # CORE PROCESSING LOOP (CITRA DIGITAL PROCESSING)
    # ==========================================
    def process_image_frame(self):
        ret, frame = self.capture.read()
        if not ret:
            return

        # 1. Operasi Pembalikan Citra (Mirroring)
        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        
        # 2. Konversi Ruang Warna (BGR ke RGB untuk pemrosesan array koordinat)
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        analysis_result = self.face_mesh.process(rgb_image)
        
        is_drowsy = False
        is_yawning = False

        if analysis_result.multi_face_landmarks:
            self.FaceDetected.setText("Yes")
            raw_landmarks = analysis_result.multi_face_landmarks[0].landmark
            
            # Perhitungan Teknis Geometri Wajah Mandiri
            left_ear, l_eye_pts = self.extract_eye_aspect_ratio(raw_landmarks, LEFT_EYE, w, h)
            right_ear, r_eye_pts = self.extract_eye_aspect_ratio(raw_landmarks, RIGHT_EYE, w, h)
            current_ear = (left_ear + right_ear) / 2.0
            
            current_mar, mouth_pts = self.extract_mouth_aspect_ratio(raw_landmarks, MOUTH_OUTER, w, h)
            
            # Tampilkan data numerik pcd ke UI Label Qt
            self.earValue.setText(f"{current_ear:.3f}")
            self.marValue.setText(f"{current_mar:.3f}")
            
            # --- CODING MANUAL DRAWING ---
            for point in l_eye_pts + r_eye_pts:
                cv2.circle(frame, point, 2, (255, 255, 0), -1)
                
            for i in range(len(mouth_pts)):
                cv2.circle(frame, mouth_pts[i], 2, (0, 255, 0), -1)
                if i > 0:
                    cv2.line(frame, mouth_pts[i-1], mouth_pts[i], (0, 200, 0), 1)
            
            for idx in EYEBROWS:
                pt = (int(raw_landmarks[idx].x * w), int(raw_landmarks[idx].y * h))
                cv2.circle(frame, pt, 2, (0, 255, 255), -1)
                
            for idx in NOSE_BRIDGE:
                pt = (int(raw_landmarks[idx].x * w), int(raw_landmarks[idx].y * h))
                cv2.circle(frame, pt, 3, (0, 0, 255), -1)
                
            for idx in JAW_LINE:
                pt = (int(raw_landmarks[idx].x * w), int(raw_landmarks[idx].y * h))
                cv2.circle(frame, pt, 2, (255, 0, 255), -1)

            # --- KONDISI LOGIKA ALARM SENSOR ---
            if current_ear < self.EAR_THRESHOLD:
                self.blink_counter += 1
            else:
                self.blink_counter = 0
                
            if current_mar > self.MAR_THRESHOLD:
                is_yawning = True

            if self.blink_counter >= self.CONSEC_FRAMES or is_yawning:
                is_drowsy = True
                
            self.drowsyCounter.setText(str(self.blink_counter))
            
        else:
            self.FaceDetected.setText("No")
            self.earValue.setText("-")
            self.marValue.setText("-")
            self.blink_counter = 0
            self.drowsyCounter.setText("0")

        # --- UPDATE INTERFACE & LOGIKA AUDIO ALARM MP3 LOOPING ---
        if is_drowsy:
            self.statusBadge.setText("STATUS: DROWSY (BAHAYA)")
            self.statusBadge.setStyleSheet("background-color: #ef4444; color: white; font-weight: bold; border-radius: 8px; padding: 10px;")
            
            # Jika MP3 sedang tidak berbunyi, putar alarmnya
            if self.player.state() != QMediaPlayer.PlayingState:
                self.player.play()
                
            # Logika Looping MP3 Manual: jika durasi lagu habis, dia balik lagi ke awal otomatis
            if self.player.state() == QMediaPlayer.StoppedState and is_drowsy:
                self.player.play()
        else:
            if self.is_running and analysis_result.multi_face_landmarks:
                self.statusBadge.setText("STATUS: NORMAL")
                self.statusBadge.setStyleSheet("background-color: #10b981; color: white; font-weight: bold; border-radius: 8px; padding: 10px;")
            
            # Otomatis matikan alarm MP3 jika kondisi sudah aman/normal kembali
            self.player.stop()

        # --- PERHITUNGAN REAL-TIME FPS ---
        self.frame_count += 1
        current_time = time.time()
        if current_time - self.last_fps_time >= 1.0:
            self.fps = self.frame_count
            self.fpsCounter.setText(str(self.fps))
            self.frame_count = 0
            self.last_fps_time = current_time

        # --- RENDERING CITRA KE COMPONENT QT DESIGNER ---
        rgb_render = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        qt_image = QtGui.QImage(rgb_render.data, rgb_render.shape[1], rgb_render.shape[0], QtGui.QImage.Format_RGB888)
        pixmap_data = QtGui.QPixmap.fromImage(qt_image)
        self.videoLabel.setPixmap(pixmap_data.scaled(self.videoLabel.size(), QtCore.Qt.KeepAspectRatio))

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    ui_window = DrowsinessDetectionSystem()
    ui_window.show()
    sys.exit(app.exec_())