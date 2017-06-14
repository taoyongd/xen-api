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


val introduce:
  __context:Context.t ->
  vM:[ `VM ] Ref.t ->
  hostbus:string ->
  hostaddr:string ->
  sn:string -> [`USB] Ref.t

val attach:
  __context:Context.t ->
  self:API.ref_USB -> unit

val detach:
  __context:Context.t ->
  self:[`USB] API.Ref.t -> unit

val destroy:
  __context:Context.t ->
  self:[`USB] API.Ref.t -> unit