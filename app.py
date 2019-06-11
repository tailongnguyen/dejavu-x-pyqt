import warnings
import json
import sys
import random
import time

warnings.filterwarnings("ignore")

from dejavu.recognize import FileRecognizer, MicrophoneRecognizer
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, \
                            QPushButton, QHBoxLayout, QVBoxLayout, \
                            QLabel, QListWidget, QAction, qApp, \
                            QFileDialog, QProgressBar, QTableWidget, \
                            QTableWidgetItem, QInputDialog, QLineEdit, \
                            QRadioButton, QSlider
from PyQt5.QtGui import QIcon, QColor, QPixmap
from PyQt5.QtCore import pyqtSlot, Qt, QThread, pyqtSignal
from dejavu import Dejavu

class CollapsibleBox(QtWidgets.QWidget):
    def __init__(self, title="", parent=None):
        super(CollapsibleBox, self).__init__(parent)

        self.toggle_button = QtWidgets.QToolButton(text=title, checkable=True, checked=False)
        self.toggle_button.setStyleSheet("QToolButton { border: none; }")
        self.toggle_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        self.toggle_button.pressed.connect(self.on_pressed)

        self.toggle_animation = QtCore.QParallelAnimationGroup(self)

        self.content_area = QtWidgets.QScrollArea(maximumHeight=0, minimumHeight=0)
        self.content_area.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.content_area.setFrameShape(QtWidgets.QFrame.NoFrame)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toggle_button)
        lay.addWidget(self.content_area)

        self.toggle_animation.addAnimation(QtCore.QPropertyAnimation(self, b"minimumHeight"))
        self.toggle_animation.addAnimation(QtCore.QPropertyAnimation(self, b"maximumHeight"))
        self.toggle_animation.addAnimation(QtCore.QPropertyAnimation(self.content_area, b"maximumHeight"))

    @QtCore.pyqtSlot()
    def on_pressed(self):
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(QtCore.Qt.ArrowType.DownArrow if not checked else QtCore.Qt.ArrowType.RightArrow)
        self.toggle_animation.setDirection(QtCore.QAbstractAnimation.Forward if not checked else QtCore.QAbstractAnimation.Backward)
        self.toggle_animation.start()

    def setContentLayout(self, layout):
        lay = self.content_area.layout()
        del lay
        self.content_area.setLayout(layout)
        collapsed_height = self.sizeHint().height() - self.content_area.maximumHeight()
        content_height = layout.sizeHint().height()
        for i in range(self.toggle_animation.animationCount()):
            animation = self.toggle_animation.animationAt(i)
            animation.setDuration(500)
            animation.setStartValue(collapsed_height)
            animation.setEndValue(collapsed_height + content_height)

        content_animation = self.toggle_animation.animationAt(self.toggle_animation.animationCount() - 1)
        content_animation.setDuration(500)
        content_animation.setStartValue(0)
        content_animation.setEndValue(content_height)


class FingerprintThread(QThread):
    """
    Runs a counter thread.
    """
    countChanged = pyqtSignal(int, int)

    def __init__(self, djv, songs):
        super().__init__()
        self.djv = djv
        self.songs = songs

    def run(self):
        count = 0
        while count < len(self.songs):
            filename = self.songs[count]
            self.djv.fingerprint_file(filename, filename.split("/")[-1].split(".mp3")[0])
            # time.sleep(2)
            self.countChanged.emit(count + 1, len(self.songs))
            count +=1

class RecognizeThread(QThread):
    """
    Runs a waiting thread.
    """
    done = pyqtSignal(list)

    def __init__(self, djv, seconds):
        super().__init__()
        self.djv = djv
        self.secs = seconds

    def run(self):
        recognized_songs = self.djv.recognize(MicrophoneRecognizer, seconds=self.secs)
        self.done.emit(recognized_songs)
            

class App(QMainWindow):

    def __init__(self, config):
        super().__init__()
        self.title = 'Dejavu'
        self.left = 300
        self.top = 300
        self.width = 1000
        self.height = 1500

        self.param_manager = None
        self.manager = None

        self.initDejavu(config)
        self.initUI()

    def initUI(self):
        exitAct = QAction(QIcon('images/quit.png'), '&Exit', self)        
        exitAct.setShortcut('Ctrl+Q')
        exitAct.setStatusTip('Exit application')
        exitAct.triggered.connect(qApp.quit)

        showSongsList = QAction(QIcon('images/db.png'), '&Fingerprints', self)
        showSongsList.setShortcut('Ctrl+F')
        showSongsList.setStatusTip('Show fingerprinted songs')
        showSongsList.triggered.connect(self.show_songs_list)
        
        changeNumberShow = QAction(QIcon("images/table.png"), '&Result Table', self)
        changeNumberShow.setShortcut('Ctrl+T')
        changeNumberShow.setStatusTip('Change format of results table.')
        changeNumberShow.triggered.connect(self.show_change_result_table)
        
        recogParams = QAction(QIcon("images/gear.png"), '&Settings', self)
        recogParams.setShortcut('Ctrl+S')
        recogParams.setStatusTip('Change parameters of recognizer.')
        recogParams.triggered.connect(self.show_recog_param_tweak)

        menubar = self.menuBar()
        file_menu = menubar.addMenu('&File')
        file_menu.addAction(showSongsList)
        file_menu.addAction(exitAct)

        preferences = menubar.addMenu('&Preferences')
        preferences.addAction(changeNumberShow)
        preferences.addAction(recogParams)

        
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)
        self.statusBar().showMessage("Ready")

        self.main_widget = QWidget(self)

        self.button = QPushButton('Start recognizing')
        self.button.setToolTip('Click here to start recognizing songs.')
        self.button.setFixedWidth(300)
        self.button.clicked.connect(self.on_click)

        h1 = QHBoxLayout()
        h1.setAlignment(Qt.AlignHCenter)
        h1.addStretch()
        h1.addWidget(self.button)
        h1.addStretch()

        self.labelA = QLabel('Detected results will be shown here.')
        self.labelA.setAlignment(Qt.AlignCenter)
        
        self.labelB = QLabel(self)
        pixmap = QPixmap('images/logo.png')
        self.labelB.resize(300, 145)
        self.labelB.setPixmap(pixmap)
        self.labelB.setAlignment(Qt.AlignCenter)
        
        self.tableWidget = QTableWidget()
        self.tableWidget.setRowCount(4)
        self.tableWidget.setColumnCount(2)
        self.tableWidget.setMaximumWidth(1000)
        self.tableWidget.setHorizontalHeaderLabels(["Song", "Confidence"])

        header = self.tableWidget.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)

        vheader = self.tableWidget.verticalHeader()
        vheader.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        vheader.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        
        h2 = QHBoxLayout()
        h2.setAlignment(Qt.AlignHCenter)
        h2.addWidget(self.tableWidget)

        v1 = QVBoxLayout()
        v1.setAlignment(Qt.AlignHCenter)
        v1.addStretch()
        v1.addWidget(self.labelB)
        v1.addLayout(h1)
        v1.addWidget(self.labelA)
        v1.addLayout(h2)
        v1.addStretch()

        self.main_widget.setLayout(v1)
        self.setCentralWidget(self.main_widget)

        self.tableWidget.hide()
        self.show()

    def initDejavu(self, config):
        params = {
            'window_size': 4096,
            'overlap_ratio': 0.5,
            'fan_value': 15,
            'amp_min': 10,
            'neighborhood_size': 20,
            'max_hash_time_delta': 200
        }

        self.djv = Dejavu(params, config)
        self.secs = 5
        self.params = params
        

    @pyqtSlot()
    def on_click(self):
        self.labelA.setText("Recognizing ...")
        self.recog_thread = RecognizeThread(self.djv, self.secs)
        self.recog_thread.done.connect(self.on_done_recognizing)
        self.recog_thread.start()

        self.button.setDisabled(True)
    
    def on_done_recognizing(self, recognized_songs):

        if recognized_songs is None:
            print("Nothing recognized -- did you play the song out loud so your mic could hear it? :)")
            self.labelA.setText("Nothing recognized :( \n Did you play the song out loud so your mic could hear it?")
        else:
            self.labelA.setText("From mic with {} seconds we recognized {} songs".format(self.secs, len(recognized_songs)))
            self.tableWidget.setRowCount(len(recognized_songs))
            self.tableWidget.setColumnCount(2)

            for i, song in enumerate(recognized_songs):
                self.tableWidget.setItem(i, 0, QTableWidgetItem(song['song_name']))
                self.tableWidget.setItem(i, 1, QTableWidgetItem(str(song['confidence'])))

            self.tableWidget.setEditTriggers(QTableWidget.NoEditTriggers)
            self.tableWidget.show()
        
        self.button.setDisabled(False)

    def update_seconds(self, secs):
        self.secs = secs
        print("Seconds value has been set to {}".format(secs))

    def update_params(self, new_params):
        self.djv.params = new_params
        self.params = new_params
        print("Params has been set to {}".format(new_params))

    @pyqtSlot()
    def show_songs_list(self):
        self.manager = FingerPrintManager(self.djv)
        self.manager.show()

    @pyqtSlot()
    def show_change_result_table(self):
        i, okPressed = QInputDialog.getInt(self, "Number of top results to be shown","Interger", 5, 1, 10, 1)
        if okPressed:
            self.djv.top_res = i
            print("Set top-results to {}".format(i))

    @pyqtSlot()
    def show_recog_param_tweak(self):
        self.param_manager = ParamManager(self, self.secs, self.params)
        self.param_manager.show()

    def closeEvent(self, event):
        # do stuff
        if self.manager is not None:
            self.manager.close()
        
        if self.param_manager is not None:
            self.param_manager.close()

class ParamManager(QWidget):

    def __init__(self, parent, secs, params):
        super().__init__()
        self.parent = parent
        self.secs = secs
        self.params = params
        self.initUI()

    def initUI(self):
        self.sec_label = QLabel()
        self.sec_label.setText('Seconds:')
        self.sec_line = QLineEdit()
        self.sec_line.setText(str(self.secs))
        self.sec_line.setFixedWidth(300)

        self.confirm_btn = QPushButton("Confirm")
        self.confirm_btn.setFixedWidth(300)
        self.confirm_btn.clicked.connect(self.on_confirm)

        h = QHBoxLayout()
        h.setAlignment(Qt.AlignCenter)
        h.addWidget(self.confirm_btn)

        self.ws_label = QLabel()
        self.ws_label.setText("Window Size:")
        self.ws_line = QLineEdit()
        self.ws_line.setText(str(self.params['window_size']))
        self.ws_line.setFixedWidth(300)
        self.ws_line.setToolTip("Size of the FFT window, affects frequency granularity")

        self.ovr_label = QLabel()
        self.ovr_label.setText("Overlap Ratio:")
        self.ovr_line = QLineEdit()
        self.ovr_line.setText(str(self.params['overlap_ratio']))
        self.ovr_line.setFixedWidth(300)
        self.ovr_line.setToolTip("Ratio by which each sequential window overlaps the last and the next window. \n Higher overlap will allow a higher granularity of offset matching, but potentially more fingerprints.")

        self.fv_label = QLabel()
        self.fv_label.setText("Fan Value:")
        self.fv_line = QLineEdit()
        self.fv_line.setText(str(self.params['fan_value']))
        self.fv_line.setFixedWidth(300)
        self.fv_line.setToolTip("Degree to which a fingerprint can be paired with its neighbors, \nhigher will cause more fingerprints, but potentially better accuracy.")

        self.at_label = QLabel()
        self.at_label.setText("Amplitude Threshold:")
        self.at_line = QLineEdit()
        self.at_line.setText(str(self.params['amp_min']))
        self.at_line.setFixedWidth(300)
        self.at_line.setToolTip(" Minimum amplitude in spectrogram in order to be considered a peak. \nThis can be raised to reduce number of fingerprints, but can negatively affect accuracy.")

        self.pns_label = QLabel()
        self.pns_label.setText("Peak Neighborhood Size:")
        self.pns_line = QLineEdit()
        self.pns_line.setText(str(self.params['neighborhood_size']))
        self.pns_line.setFixedWidth(300)
        self.pns_line.setToolTip("Number of cells around an amplitude peak in the spectrogram in order \nfor Dejavu to consider it a spectral peak. Higher values mean less \nfingerprints and faster matching, but can potentially affect accuracy.")

        self.mhtd_label = QLabel()
        self.mhtd_label.setText("Max Hash Time Delta:")
        self.mhtd_line = QLineEdit()
        self.mhtd_line.setText(str(self.params['max_hash_time_delta']))
        self.mhtd_line.setFixedWidth(300)
        self.mhtd_line.setToolTip("Thresholds on how close or far fingerprints can be in time in order \nto be paired as a fingerprint. If your max is too low, higher values of \nfan_value may not perform as expected.")

        v = QVBoxLayout(self)
        v.addStretch()
        v.addWidget(self.sec_label)
        v.addWidget(self.sec_line)
        v.addWidget(self.ws_label)
        v.addWidget(self.ws_line)
        v.addWidget(self.ovr_label)
        v.addWidget(self.ovr_line)
        v.addWidget(self.fv_label)
        v.addWidget(self.fv_line)
        v.addWidget(self.at_label)
        v.addWidget(self.at_line)
        v.addWidget(self.pns_label)
        v.addWidget(self.pns_line)
        v.addWidget(self.mhtd_label)
        v.addWidget(self.mhtd_line)
    
        v.addStretch()

        v.addLayout(h)

        self.setWindowTitle('Preferences')
        self.setGeometry(500, 500, 1100, 550)
        self.setFixedSize(400, 1000)

    def on_confirm(self):
        try:
            if int(self.sec_line.text()) <= 20:
                self.parent.update_seconds(int(self.sec_line.text()))
            else:
                self.sec_label.setText('Seconds: (*)')
                self.sec_label.setStyleSheet("color: red")
                self.sec_label.setToolTip("must be integer between 1 and 20")
                return

        except:
            self.sec_label.setText('Seconds: (*)')
            self.sec_label.setStyleSheet("color: red")
            self.sec_label.setToolTip("must be integer between 1 and 20")
            return

        new_params = {
            'window_size': int(self.ws_line.text()),
            'overlap_ratio': float(self.ovr_line.text()),
            'fan_value': int(self.fv_line.text()),
            'amp_min': int(self.at_line.text()),
            'neighborhood_size': int(self.pns_line.text()),
            'max_hash_time_delta': int(self.mhtd_line.text())
        }

        self.params = new_params
        self.parent.update_params(new_params)
        self.close()
        

class FingerPrintManager(QWidget):

    def __init__(self, djv):
        super().__init__()
        self.djv = djv
        self.initUI()

    def initUI(self):
        songs = [s['song_name'] for s in self.djv.db.get_songs()]
        songs_list = QListWidget(self)
        songs_list.setFixedSize(800, 400)
        for s in songs:
            songs_list.addItem(s)
        
        self.button = QPushButton("New song")
        self.button.setToolTip('Click here to fingerprint a new song.')
        self.button.clicked.connect(self.open_file)

        self.progress = QProgressBar()
        self.progress.setFixedSize(800, 30)
        
        self.v1 = QVBoxLayout(self)
        self.v1.setAlignment(Qt.AlignHCenter)
        self.v1.addStretch()
        self.v1.addWidget(songs_list)
        self.v1.addStretch()
        self.v1.addWidget(self.button)
        self.v1.addStretch()
        self.v1.addWidget(self.progress)
        self.v1.addStretch()

        self.progress.hide()

        self.setWindowTitle("Fingerprints Manager")
        self.setGeometry(500, 500, 1100, 550)
        self.setFixedSize(1100, 550)

    def open_file(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        files, _ = QFileDialog.getOpenFileNames(self, "QFileDialog.getOpenFileNames()", "","All Files (*);;MP3 Files (*.mp3)", options=options)
        
        self.fingerprint(files)
    
    def fingerprint(self, files):
        if len(files) == 0:
            return "Empty"

        print("Start fingerprinting {}".format(files))
        self.button.setDisabled(True)

        self.progress.setMaximum(len(files))
        self.progress.setValue(0)
        self.progress.show()

        self.prog = FingerprintThread(self.djv, files)
        self.prog.countChanged.connect(self.on_count_change)
        self.prog.start()
    
    def on_count_change(self, value, max_value):
        if value < max_value:
            self.progress.setValue(value)
        else:
            self.button.setDisabled(False)
            self.progress.hide()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    with open("dejavu.cnf.SAMPLE") as f:
        config = json.load(f)

    ex = App(config)
    sys.exit(app.exec_())