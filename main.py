import os, shutil, threading
from datetime import datetime
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
import core, data

Window.clearcolor = (0.08, 0.09, 0.12, 1)


class LotoApp(App):
    title = "Loto Bonheur"

    def build(self):
        self.path = os.path.join(self.user_data_dir, "loto_bonheur.txt")
        if not os.path.exists(self.path):  # première ouverture : copie du fichier fourni
            shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), "loto_bonheur.txt"), self.path)
        root = BoxLayout(orientation="vertical", padding=8, spacing=6)
        self.status = Label(size_hint_y=None, height=60, halign="center", text_size=(Window.width - 20, None))
        root.add_widget(self.status)
        self.spin = Spinner(size_hint_y=None, height=48, text="Choisir un tirage")
        root.add_widget(self.spin)
        for txt, fn in [("Moteur SELECT (tirage choisi)", self.do_select), ("Moteur VIP", self.do_vip),
                        ("Les deux moteurs", self.do_both), ("Backtest VIP", self.do_backtest),
                        ("Mise à jour automatique", self.do_update), ("Ajouter un tirage", self.add_popup)]:
            root.add_widget(Button(text=txt, size_hint_y=None, height=46, on_release=lambda _b, f=fn: f()))
        sv = ScrollView()
        self.out = Label(text="", size_hint_y=None, halign="left", valign="top", markup=False)
        self.out.bind(width=lambda *a: setattr(self.out, "text_size", (self.out.width, None)),
                      texture_size=lambda *a: setattr(self.out, "height", self.out.texture_size[1]))
        sv.add_widget(self.out)
        root.add_widget(sv)
        self.refresh()
        return root

    def refresh(self):
        self.draws = data.load(self.path)
        self.names = sorted({d["name"] for d in self.draws})
        self.spin.values = self.names
        if self.spin.text not in self.names:
            self.spin.text = "Digital Reveil 8h" if "Digital Reveil 8h" in self.names else self.names[0]
        last = self.draws[-1]
        self.status.text = f"{len(self.draws)} tirages\nDernier : {last['day']} - {last['name']}"

    def run(self, fn, *args):  # calcul en arrière-plan pour ne pas figer l'écran
        self.out.text = "Calcul en cours..."
        def work():
            try:
                res = fn(*args)
            except Exception as e:
                res = f"Erreur : {type(e).__name__} {e}"
            Clock.schedule_once(lambda dt: setattr(self.out, "text", res))
        threading.Thread(target=work, daemon=True).start()

    def do_select(self):
        self.run(core.select_text, self.draws, self.spin.text)

    def do_vip(self):
        self.run(core.vip_text, self.draws)

    def do_both(self):
        self.run(lambda: core.vip_text(self.draws) + "\n\n" + core.select_text(self.draws, self.spin.text))

    def do_backtest(self):
        self.run(core.backtest_text, self.draws)

    def do_update(self):
        def f():
            msg = core.auto_update(self.path, self.draws)
            Clock.schedule_once(lambda dt: self.refresh())
            return msg
        self.run(f)

    def add_popup(self):
        box = BoxLayout(orientation="vertical", spacing=6, padding=6)
        date = TextInput(hint_text="Date jj/mm/aaaa", multiline=False, size_hint_y=None, height=44,
                         text=datetime.now().strftime("%d/%m/%Y"))
        nom = Spinner(text=self.spin.text, values=self.names, size_hint_y=None, height=44)
        g = TextInput(hint_text="Gagnants : 5 numéros", multiline=False, size_hint_y=None, height=44)
        m = TextInput(hint_text="Machines : 5 numéros (vide si aucune)", multiline=False, size_hint_y=None, height=44)
        msg = Label(size_hint_y=None, height=40)
        for w in (date, nom, g, m, msg):
            box.add_widget(w)
        pop = Popup(title="Ajouter un tirage", content=box, size_hint=(0.95, 0.7))

        def save(*_):
            try:
                dt = datetime.strptime(date.text.strip(), "%d/%m/%Y")
                gg = [int(x) for x in g.text.replace(",", " ").split()]
                mm = [int(x) for x in m.text.replace(",", " ").split()]
            except ValueError:
                msg.text = "Date ou numéros invalides"
                return
            d = {"day": f"{data.JOURS[dt.weekday()]} {dt:%d/%m/%Y}", "date": dt, "name": nom.text, "g": gg, "m": mm}
            ok, bad = data.append_new(self.path, [d], set(self.names))
            if ok:
                self.refresh()
                pop.dismiss()
                self.out.text = "Tirage ajouté."
            else:
                msg.text = bad[0][1]
        box.add_widget(Button(text="Enregistrer", size_hint_y=None, height=46, on_release=save))
        pop.open()


if __name__ == "__main__":
    LotoApp().run()
