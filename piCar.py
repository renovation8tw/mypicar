from flask import Flask, render_template, request, Response, jsonify, redirect
import math, os, sqlite3, shutil
import RPi.GPIO as GPIO
import cv2
from Bluetin_Echo import Echo
from time import sleep

app = Flask(__name__)

camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH,320)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT,240)
# *** FPS is 30 by default ***
# fps = camera.get(cv2.CAP_PROP_FPS)
# print("Image FPS:",fps)

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

in1 = 18
in2 = 23
in3 = 24
in4 = 25

GPIO.setup(in1, GPIO.OUT)
pwm1 = GPIO.PWM(in1, 100)
pwm1.start(0) 
GPIO.setup(in2, GPIO.OUT)
pwm2 = GPIO.PWM(in2, 100)
pwm2.start(0) 
GPIO.setup(in3, GPIO.OUT)
pwm3 = GPIO.PWM(in3, 100)
pwm3.start(0) 
GPIO.setup(in4, GPIO.OUT)
pwm4 = GPIO.PWM(in4, 100)
pwm4.start(0) 

# 定義最大車輪轉速
maxSpeed = 100
# 定義避障距離
obscaleDistance = 25
# 是否開啟避障功能旗標值
isAvoid = False
# 自動避障參數
TRIGGER_PIN = 16
ECHO_PIN = 12
speed_of_sound = 340
echo = Echo(TRIGGER_PIN, ECHO_PIN, speed_of_sound)
samples = 5
# 定義拍照存檔序號
imgCounter = 1

def stop():
    pwm1.start(0)
    pwm2.start(0)
    pwm3.start(0)
    pwm4.start(0)
    
def forward(lSpeed,rSpeed):
    pwm1.start(0)
    pwm2.start(lSpeed)
    pwm3.start(0)
    pwm4.start(rSpeed)

def backward(lSpeed,rSpeed):
    pwm1.start(lSpeed)
    pwm2.start(0)
    pwm3.start(rSpeed)
    pwm4.start(0)   
    
def turn_right(speed):
    pwm1.start(0)
    pwm2.start(speed)
    pwm3.start(0)
    pwm4.start(0)  
    
def turn_left(speed):
    pwm1.start(0)
    pwm2.start(0)
    pwm3.start(0)
    pwm4.start(speed)     

def generate_frame():
    # while True:
    while (camera.isOpened()):
        success, frame = camera.read()
        # frame = cv2.flip(frame,-1)
        if not success:
            print('Failed to read from camera!')
            break
        else:
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    # camera.release()

def obscale_avoid():
    global obscaleDistance, maxSpeed, isAvoid
    # 因為超音波感應器裝在車尾，所以車子行進方向前後顛倒
    while (isAvoid):
        result = echo.read("cm", samples)
        print(result, "cm")
        if result <= obscaleDistance:  # 在前方有障礙物
            stop()
            sleep(1)
            if result < (obscaleDistance-5):  # 太近, 先退...
                forward(maxSpeed*0.5, maxSpeed*0.5)
                sleep(1)
                stop()

            import random                           #
            if random.randint(1, 100) > 50:
                turn_left(maxSpeed*0.5)
                sleep(1)
                stop()
            else:
                turn_right(maxSpeed*0.5)
                sleep(1)
                stop()  

        backward(maxSpeed*0.5, maxSpeed*0.5) 
    stop()


@app.route("/")
def index():
    return render_template('stick_control.html')

@app.route("/avoid")
def avoid():
    return render_template('obscale_avoid.html')

@app.route("/navigate")
def guide():
    return render_template('auto_navigate.html')

@app.route("/confpage")
def confPage():
    return render_template('config.html')

@app.route("/model")
def model():
    return render_template('model.html')

@app.route("/admin")
def admin():
    return render_template('img_admin.html')


# ------ 以下為Ajax請求的回應 -------

@app.route('/video_feed')
def video_feed():
    return Response(generate_frame(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/stick",methods=['GET'])
def handleStick():
    global maxSpeed
    if 'x' in request.args:
        stickX = float(request.args.get('x'))
    if 'y' in request.args:
        stickY = float(request.args.get('y'))
    # return "x=" + str(stickX) + " ;y=" + str(stickY)
    h = (stickX**2 + stickY**2)**0.5
    if h == 0:
        stop()
        return "(0,0)"
    majorSpeed = maxSpeed * h
    minorSpeed = majorSpeed * math.asin(stickY/h)/(math.pi/2)
    if stickX >= 0 and stickY > 0 :
        backward(majorSpeed,minorSpeed)
    elif stickX < 0 and stickY > 0 :
        backward(minorSpeed,majorSpeed)
    elif stickX <= 0 and stickY <=0 :
        forward(-minorSpeed,majorSpeed)
    else :
        forward(majorSpeed,-minorSpeed)

    return "({},{})".format(stickX,stickY)

@app.route("/obscale",methods=['GET'])
def handleAvoid():
    global isAvoid
    argAvoid = request.args.get('avoid')
    if (argAvoid == "true") :
        isAvoid = True
        # print(isAvoid)
        obscale_avoid()
        return "避障: ON"          # 基於Python的同步特性，此行不會被執行
    else:
        isAvoid = False
        # print(isAvoid)
        # stop()
        return "避障: OFF"
    
@app.route("/auto",methods=['GET'])
def handleGuide():
    # isGuide = request.args.get("guide")
    # if isGuide == "true":
    #     return "Automated Guided: ON"
    # else:
    #     return "Automated Guided: OFF"
    classPrediction = request.args.get("class")
    if classPrediction == 'FW':
        forward(50,50)
    elif classPrediction == 'LEFT':
        turn_left(50)
    elif classPrediction == 'SHIFT-L':
        forward(25,50)
    elif classPrediction == 'SHIFT-R':
        forward(50,25)
    else:
        stop()

    return classPrediction

@app.route("/path", methods=['GET'])
def handlePath():
    global maxSpeed
    goTo = request.args.get("go","forward")
    if goTo == 'forward':
        forward(maxSpeed, maxSpeed)
    elif goTo == 'back':
        backward(maxSpeed, maxSpeed)
    elif goTo == 'right':
        turn_right(maxSpeed*0.5)
    elif goTo == 'left'  :
        turn_left(maxSpeed*0.5)
    else :
        stop()

    return "Go: " + goTo

@app.route("/config", methods=['GET'])
def handleConfig():
    global maxSpeed, obscaleDistance
    if 'speed' in request.args:
        maxSpeed = int(request.args.get('speed'))
    if 'distance' in request.args:
        obscaleDistance = float(request.args.get('distance'))
    return '{"Speed":' + str(maxSpeed) + ',"Distance":' + str(obscaleDistance) + '}'

@app.route('/createClassFolder',methods=['POST'])
def createClassFolder():
    if request.method == 'POST':
        modelClass = request.values['class']
        # print(modelClass)
        imgPath = 'static/imgClass/' + modelClass
        if not (os.path.exists(imgPath)):
            os.mkdir(imgPath)

        conn = sqlite3.connect("imgClass.db")
        cursor = conn.cursor()
        # sql = "select className from class where className = '" + modelClass + "'"
        result = cursor.execute("select classname from class where classname = '" + modelClass + "'" )

        if (len(result.fetchall()) == 0) :
            cursor.execute("insert into class (classname) values ('" + modelClass + "')")
            conn.commit()
            strReturn = "已建立新類別: '" + modelClass + "'"  
        else :
            strReturn = "'" + modelClass + "' 類別已存在."
            
        conn.close()
        return strReturn

@app.route('/photo',methods=['GET'])
def handleCamera():
    global imgCounter
    if 'class' in request.args:
        if (camera.isOpened()):
            result, frame = camera.read()
            # if (not result):
            #     return 'Failed to grab frame...'
            #  儲存照片至指定路徑。若路徑資料夾不存在，則建立資料夾；若照片檔已存在，則覆寫之。
            modelClass = request.args.get('class')
            imgPath = 'static/imgClass/' + modelClass
            if not (os.path.exists(imgPath)):
                os.mkdir(imgPath)
            imgName = modelClass+'_0{}.png'.format(imgCounter) if imgCounter<10 else modelClass+'_{}.png'.format(imgCounter)
            cv2.imwrite(imgPath+'/'+imgName,frame)
            # 儲存記錄至資料表：若img資料表中查無相同的imgname才可新增；若有相同者則保留原來的，不用增加
            conn = sqlite3.connect("imgClass.db")
            cursor = conn.cursor()
            result = cursor.execute("select imgname from img where imgname = '" + imgName + "'" )
            if (len(result.fetchall()) == 0) :
                cursor.execute("insert into img values (?, ?)",(imgName, modelClass))
                conn.commit()
                conn.close()
            
            imgCounter += 1
            return '已擷取影像: ' + imgName

@app.route('/query',methods=['GET'])
def handledb():
    resHtml = []
    if 'q' in request.args:
        conn = sqlite3.connect('imgClass.db')
        cursor = conn.cursor()
        q =  request.args.get('q')
        if q == '1':              #1: buery by class
            sql = 'select classname from class'
            result = cursor.execute(sql)
            thead = '<tr><th>Class</th></tr>'
            resHtml.append(thead)
            tbody = ''
            for row in result:
                tbody += '<tr><td><i class="far fa-folder"></i>' + row[0] + '</td></tr>'
            resHtml.append(tbody)
            panelInfo = '/'
            resHtml.append(panelInfo)
        elif q == '2':            # 2: query by image
            if 'c' in request.args:
                c = request.args.get('c')
                sql = "select imgname, classname from img where classname ='" + c + "'"
                result = cursor.execute(sql)
                thead = '<tr><th>Image</th><th>Class</th></tr>'
                resHtml.append(thead)
                tbody = ''
                for row in result:
                    tbody += '<tr><td>' + row[0] + '</td><td>' + row[1] + '</td></tr>'
                resHtml.append(tbody)
                panelInfo = '/' + c
                resHtml.append(panelInfo)
        elif q == '3':            # 3: show the selected image 
            if ('c' in request.args) and ('i' in request.args) :
                c = request.args.get('c')
                i = request.args.get('i')
                resHtml.append('showImg')
                imgURL = '../static/imgClass/{}/{}'.format(c,i)
                resHtml.append(imgURL)
                panelInfo = "/{}/{}".format(c,i)
                resHtml.append(panelInfo)

        conn.close()
        print(resHtml)
        return jsonify(resHtml)

@app.route('/delete',methods=['POST'])
def delete():
    queryBy = request.values['queryby']
    delClass = request.values['delclass']
    conn = sqlite3.connect('imgClass.db')
    cursor = conn.cursor()
    redirectPath = ""
    resHtml = []
    SQL = []
    
    if queryBy == '1' :
        sql1 = "delete from class where classname ='{}'".format(delClass)
        sql2 = "delete from img where classname ='{}'".format(delClass)
        SQL.extend([sql1,sql2])
        shutil.rmtree('static/imgClass/' + delClass)
        redirectPath = '/query?q=1'
    else  :                 # if queryBy == 2 or 3 ,delete image...
        delImage = request.values['delimage']
        sql1 = "delete from img where imgname ='{}'".format(delImage)
        SQL.append(sql1)
        os.remove('static/imgClass/' + delClass + '/' + delImage)
        if queryBy == '2' :     
            redirectPath = '/query?q=2&c=' + delClass
        else :
            resHtml.append("imgDeleted")
            resHtml.append("影像已刪除 請回上層目錄")
    
    for sql in SQL:
        cursor.execute(sql)
        conn.commit()
    conn.close()

    if bool(redirectPath):
        return redirect(redirectPath) 
    else :
        return resHtml

# ------ 以上為Ajax請求的回應 ------

if __name__ == '__main__':
    # 停用 debug=true 才不會出現找不到攝影機的錯誤訊息
    app.run("0.0.0.0")
    # app.run('0.0.0.0',debug=True)
