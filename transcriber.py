import PySimpleGUI as sg
from pydub import AudioSegment
import os.path
import requests
import json

language_choices = ["Arabic", "German", "English (Australia)", "English (UK)", "English (US)", "Spanish (Argentina)", "Spanish (Spain)", "Spanish (Chile)", "Spanish (Colombia)", "Spanish (Mexico)", "Spanish (Peru)", "French (Canada)", "French (France)", "Italian", "Japanese", "Korean", "Dutch", "Portuguese (Brazil)", "Mandarin Chinese"]

langauge2modelname = {"Arabic":"ar-AR_BroadbandModel",
    "German":"de-DE_BroadbandModel",
    "English (Australia)":"en-AU_BroadbandModel",
    "English (UK)":"en-GB_BroadbandModel",
    "English (US)":"en-US_BroadbandModel",
    "Spanish (Argentine)":"es-AR_BroadbandModel",
    "Spanish (Spain)":"es-ES_BroadbandModel",
    "Spanish (Chile)":"es-CL_BroadbandModel",
    "Spanish (Colombia)":"es-CO_BroadbandModel",
    "Spanish (Mexico)":"es-MX_BroadbandModel",
    "Spanish (Peru)":"es-PE_BroadbandModel",
    "French (Canada)":"fr-CA_BroadbandModel",
    "French (France)":"fr-FR_BroadbandModel",
    "Italian":"it-IT_BroadbandModel",
    "Japanese":"ja-JP_BroadbandModel",
    "Korean":"ko-KR_BroadbandModel",
    "Dutch":"nl-NL_BroadbandModel",
    "Portuguese (Brazil)":"pt-BR_BroadbandModel",
    "Mandarin Chinese":"zh-CN_BroadbandModel"}

def make_request(api_url, api_key, filename, lang):
    file_dir = os.path.dirname(filename)
    basename, ext = os.path.split(filename)[-1].split(".")
    output_dir = os.path.join(file_dir, basename+"_files")
    content_type = 'audio/{}'.format(ext.lower())
    model_name = langauge2modelname[lang]

    headers = {
        'Content-Type': content_type,
    }

    params = (
        ('model', model_name),
        ('timestamps', 'true')
    )

    data = open(filename, 'rb').read()

    response = requests.post(api_url, headers=headers, params=params, data=data, auth=('apikey', api_key))

    return response.text, output_dir

def parse_results(results, is_zh_ja):
    
    plaintext = []
    timestamps = []

    for sent in results:
        this_confidence = sent["alternatives"][0]["confidence"]

        this_text = sent["alternatives"][0]["transcript"]
        if is_zh_ja:
            this_text = this_text.replace(" ", "")
                
        this_begins = sent["alternatives"][0]["timestamps"][0][1]-1
        this_ends = sent["alternatives"][0]["timestamps"][-1][2]+1

        timestamps.append( (this_begins, this_ends) )
        plaintext.append(this_text)

    return timestamps, plaintext

def seg_mp3(audiofile, ts_pairs, outdir):

    song = AudioSegment.from_mp3(audiofile)

    for pair in ts_pairs:
        seg_starts = max(0, pair[0]) * 1000
        seg_ends = pair[1] * 1000
        this_seg = song[seg_starts:seg_ends]
        seg_fname = "_{}_{}.mp3".format(str(int(seg_starts/1000)), str(int(seg_ends/1000)))
        out_fname = os.path.join(outdir, seg_fname)
        this_seg.export(out_fname, format="mp3")

def gen_fulltext(ts_pairs, sents_plain):
    
    fulltext = ""

    for graph in zip(ts_pairs, sents_plain):
        if float(graph[0][0]) < 0:
            begin = 0
        else:
            begin = float(graph[0][0])
        end = float(graph[0][1])
        fulltext += "\n\n{:.2f} -> {:.2f}\n\n".format(begin, end)
        fulltext += graph[1]
    
    return fulltext

api_frame = [
    [sg.T("URL"), sg.In(size=(45,1), key="-APIURL-")],
    [sg.T("Key"), sg.In(size=(45,1), key="-APIKEY-")]
]

file_frame = [
    [sg.In(size=(42,1), key="-FILENAME-"), sg.FileBrowse()],
    [sg.T("Choose a MP3, WAV or OGG file.")]
]

lang_frame = [
    [sg.Combo(language_choices, size=(20,1), key="-LANG-", default_value="English (UK)")]
]

window_layout = [
    [sg.T("This app helps you transcribe recordings using\na cloud service from IBM Watson.")],
    [sg.Frame("API details", api_frame)],
    [sg.Frame("Choose a file", file_frame)],
    [sg.Frame("Choose a language", lang_frame)],
    [sg.Submit("Start"), sg.Cancel("Exit")],
    [sg.T("", key="-ALERT-", size=(45,1))]
]

window = sg.Window("Watson Transcriber", window_layout, font=("Helvetica", 14), finalize=True)

try:
    with open("ibm-credentials.env") as setin:
        for line in setin.readlines():
            keyword, value = line.split("=")
            if keyword == "SPEECH_TO_TEXT_APIKEY":
                window['-APIKEY-'].update(value.strip())
            elif keyword == "SPEECH_TO_TEXT_URL":
                window['-APIURL-'].update(value.strip())
except:
    pass

while True:
    event, values = window.read()
    if event == "Exit" or event == sg.WIN_CLOSED:
        break
    elif event == "Start":
        api_url, api_key, filename, lang = values["-APIURL-"], values["-APIKEY-"], values["-FILENAME-"], values["-LANG-"]
        if not api_url or "ibm.com" not in api_url:
            window['-ALERT-'].update("SORRY DARLING. We need a valid API URL.")
        elif not api_key:
            window['-ALERT-'].update("SORRY HONEY. We need a valid API key.")
        elif not filename.endswith( (".mp3", ".ogg", ".wav") ):
            window['-ALERT-'].update("OOPS. We need an MP3, WAV or OGG file.")
        elif not lang:
            window['-ALERT-'].update("You need to specify a language.")
        else:
            window['-ALERT-'].update("Uploading...")

            if not os.path.isfile("ibm-credentials.env"):
                with open("ibm-credentials.env", "w") as setout:
                    line1 = 'SPEECH_TO_TEXT_APIKEY={}\n'.format(api_key)
                    line2 = 'SPEECH_TO_TEXT_URL={}\n'.format(api_url)
                    setout.writelines([line1, line2])

            # The subdir could become a pain point. When the user see their credentials on IBM's website, 
            # they get a root dir. But for the recognition to work, they need to manually add `/v1/recognize`.
            feedback_text, output_dir = make_request(api_url+'/v1/recognize', api_key, filename, lang)
            feedback = json.loads(feedback_text)
            
            # Saves the feedback from server.
            if not os.path.exists(output_dir):
                os.mkdir(output_dir)

            with open(os.path.join(output_dir, "feedback.json"), "w") as debug_out:
                json.dump(feedback, debug_out)
            
            window['-ALERT-'].update("Processing...")
            if "code" in feedback.keys():
                window['-ALERT-'].update("Error {}: {}".format(feedback["code"], feedback["error"]))
            else:
                is_zh_ja = lang in ["Japanese", "Mandarin Chinese"]
                results = feedback["results"]
                ts_pairs, sents_plain = parse_results(results, is_zh_ja)

                with open(os.path.join(output_dir, "_fulltext.txt"), "w") as textout:
                    textout.write(gen_fulltext(ts_pairs, sents_plain))

                seg_mp3(filename, ts_pairs, output_dir)
                window['-ALERT-'].update("Finished.")
                os.system("open {}".format(output_dir))

window.close()