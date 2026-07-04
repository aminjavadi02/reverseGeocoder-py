from offlineRevGeocoder.app.reverseGeocoder import get


def check():
    tehran = get(35.6892, 51.3890)
    print(tehran)


if __name__ == "__main__":
    check()
    print("ok")
