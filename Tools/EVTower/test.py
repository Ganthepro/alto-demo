import serial
import argparse


ap = argparse.ArgumentParser()
ap.add_argument("-s", "--slot", required=True,
    help="slot nuumber")
args = vars(ap.parse_args())


class GreenBoard:
    def __init__(self, relay_port):
        self.relay_port = relay_port

    def check_slot_state(self, subdev_id, buad=9600, timeout=1.0):
        """
        Check, is there any battery in slot?
        """

        slot = subdev_id + 1
        try:
            section1 = [1, 2, 3, 4, 5, 6]
            section2 = [7, 8, 9]
            ser = serial.Serial(self.relay_port, buad, timeout=timeout)
            if slot in section1:
                ser.write(b'Read SW@001')
            elif slot in section2:
                ser.write(b'Read SW@002')
            else:
                raise NotImplementedError('Not implemented yet')
            res = ser.read(6)
            ser.close()
            res = res.decode("utf-8")
            if res.find("@") != -1:
                get_slot_state = res.split("@")
                if len(get_slot_state) >= 2:
                    slot_state = "0x" + get_slot_state[0]
                    state_binary = int(slot_state, 0)
                    state_bi_string = f"{state_binary:0>16b}"
                    if slot in section1:
                        if state_bi_string[len(state_bi_string) - slot] == "0":
                            return False
                        else:
                            return True
                    elif slot in section2:
                        if state_bi_string[len(state_bi_string) - (slot - 6)] == "0":
                            return False
                        else:
                            return True
                else:
                    return False
        except:
            pass
        return False

    def interface_green_board(self, subdev_id, buad=9600, timeout=5.0):
        """
        Check, is there any battery in slot?
        """

        slot = subdev_id + 1
        try:
            section1 = [1, 2, 3, 4, 5, 6]
            section2 = [7, 8, 9]
            ser = serial.Serial(self.relay_port, buad, timeout=timeout)
            if slot in section1:
                print("send 1")
                ser.write(b'Read SW@001')
            elif slot in section2:
                print("send 2")
                ser.write(b'Read SW@002')
            else:
                raise NotImplementedError('Not implemented yet')
            res = ser.read(6)
            print(res)
            ser.close()
            res = res.decode("utf-8")
            print(res)
            # if res.find("@") != -1:
            #     get_slot_state = res.split("@")
            #     if len(get_slot_state) >= 2:
            #         slot_state = "0x" + get_slot_state[0]
            #         state_binary = int(slot_state, 0)
            #         state_bi_string = f"{state_binary:0>16b}"
            #         if slot in section1:
            #             if state_bi_string[len(state_bi_string) - slot] == "0":
            #                 return False
            #             else:
            #                 return True
            #         elif slot in section2:
            #             if state_bi_string[len(state_bi_string) - (slot - 6)] == "0":
            #                 return False
            #             else:
            #                 return True
            #     else:
            #         return False
        except Exception as e:
            print(f"inf ex {e}")
        return False

slot = args["slot"]
gb = GreenBoard("/dev/ttyS0")
print(gb.interface_green_board(int(slot)))
