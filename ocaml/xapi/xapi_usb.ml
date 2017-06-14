(*
 * Copyright (C) 2006-2009 Citrix Systems Inc.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU Lesser General Public License as published
 * by the Free Software Foundation; version 2.1 only. with the special
 * exception on linking described in file LICENSE.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Lesser General Public License for more details.
 *)

open Stdext
open Listext
module D = Debug.Make(struct let name="xapi" end)
open D

let autodetect_mutex = Mutex.create ()
let introduce ~__context ~vM ~hostbus ~hostaddr ~sn =
  let usb = Ref.make () and uuid = Uuid.make_uuid () in
  Db.USB.create ~__context ~ref:usb ~uuid:(Uuid.to_string uuid)
    ~vM ~hostbus ~hostaddr ~sn ~location:"" ~currently_attached:false ~version:"";
  usb


(** Throws BAD_POWER_STATE if the VM is not running *)
let assert_not_running ~__context ~vm =
  if (Db.VM.get_power_state ~__context ~self:vm)=`Suspended || (Db.VM.get_power_state ~__context ~self:vm)=`Halted then
    let expected = String.concat ", " (List.map Record_util.power_to_string [`Running]) in
    let error_params = [Ref.string_of vm; expected; Record_util.power_to_string `Suspended] in
    raise (Api_errors.Server_error(Api_errors.vm_bad_power_state, error_params))

let assert_ok_to_attach ~__context ~vm =
  assert_not_running ~__context ~vm

let assert_ok_to_detach ~__context ~vm =
  assert_not_running ~__context ~vm

let attach ~__context ~self =
  let vm = Db.USB.get_VM ~__context ~self in
  assert_ok_to_attach ~__context ~vm;
  Xapi_xenops.usb_insert ~__context ~self

let detach ~__context ~self =
  let vm = Db.USB.get_VM ~__context ~self in
  assert_ok_to_detach ~__context ~vm;
  Xapi_xenops.usb_eject ~__context ~self

let destroy ~__context ~self =
  if Db.USB.get_currently_attached ~__context ~self 
  then raise (Api_errors.Server_error(Api_errors.operation_not_allowed, ["USB is currently attached"]));
  Db.USB.destroy ~__context ~self
